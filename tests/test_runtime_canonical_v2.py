"""Focused tests for the v2 canonical plan boundary.

Covers:
- Profile setter invocation and metadata propagation
- Local trace metadata merge onto remote result trace
- V2 plan path restore publisher wiring
"""

from __future__ import annotations

import asyncio
import os
import unittest
from typing import Any
from unittest.mock import AsyncMock, MagicMock

from canonical_execution import (
    _reset_restore_publish_cache,
    build_execution_plan,
    execute_plan,
)
from comfymodal_runtime.contracts import ExecutionOptions, ExecutionPlan, RestorePlan
from comfymodal_runtime.modal_transport import ModalTransport
from comfymodal_runtime.trace import RuntimeTrace


class _Publisher:
    def __init__(self):
        self.plans = []

    def publish(self, plan):
        self.plans.append(plan)
        return 1


# ── Profile setter helper (simulates set_active_warmup_profile) ──


class _FakeProfileSetter:
    """Async callable that records the received payload and returns a canned result."""

    def __init__(self, status: str = "written"):
        self.calls: list[tuple[dict, dict | None]] = []
        self._status = status

    async def __call__(self, payload: dict, *, workspace: dict | None = None) -> dict:
        self.calls.append((payload, workspace))
        return {"status": self._status, "changed": True}


# ═══════════════════════════════════════════════════════════════════════
# TestBuildExecutionPlan
# ═══════════════════════════════════════════════════════════════════════


class TestBuildExecutionPlan(unittest.TestCase):
    def test_builds_one_frozen_plan_without_reinterpreting_options(self):
        workflow = {
            "1": {"class_type": "CLIPTextEncode", "inputs": {"text": "a cat"}},
            "2": {"class_type": "KSampler", "inputs": {"seed": 7}},
        }
        plan = build_execution_plan(
            workflow,
            prompt_id="prompt",
            client_id="client",
            modal_options={"production": {"enabled": False}, "output_format": "webp"},
            validate=False,
        )
        self.assertIsInstance(plan.execution_options, ExecutionOptions)
        self.assertFalse(plan.execution_options.production_enabled)
        self.assertEqual(plan.execution_options.output_conversion_options["format"], "webp")
        self.assertEqual(plan.source_workflow_hash, plan.workflow_hash)
        with self.assertRaises(AttributeError):
            plan.workflow = {}  # type: ignore[misc]


# ═══════════════════════════════════════════════════════════════════════
# TestExecutePlan — profile setter invocation & metadata
# ═══════════════════════════════════════════════════════════════════════


class TestExecutePlan(unittest.TestCase):
    def test_publishes_once_and_returns_one_stream_result(self):
        observed = {}

        async def stream(**kwargs):
            observed.update(kwargs)
            yield {"type": "status", "data": {"phase": "restore"}}
            yield {"type": "result", "data": {"images": [], "outputs": {}}}

        async def run():
            plan = build_execution_plan(
                {"1": {"class_type": "KSampler", "inputs": {"seed": 1}}},
                prompt_id="prompt",
                validate=False,
            )
            publisher = _Publisher()
            transport = ModalTransport(prompt_stream_fn=stream)
            result = await execute_plan(plan, transport=transport, restore_publisher=publisher)
            self.assertEqual(len(publisher.plans), 1)
            self.assertEqual(result["outputs"], {})
            self.assertIn("events", result["trace"])
            self.assertEqual(observed["workflow"], plan.to_dict()["workflow"])

        asyncio.run(run())

    def test_remote_trace_events_and_derived_fields_survive_merge(self):
        async def stream(**kwargs):
            yield {
                "type": "result",
                "data": {
                    "outputs": {},
                    "trace": {
                        "events": [
                            {
                                "name": "container_entry",
                                "process": "remote",
                                "phase": "restore",
                                "wall_unix_ns": 1,
                                "monotonic_ns": 1,
                                "metadata": {},
                            },
                            {
                                "name": "sampler_end",
                                "process": "remote",
                                "phase": "execution",
                                "wall_unix_ns": 3,
                                "monotonic_ns": 3,
                                "metadata": {},
                            },
                        ],
                        "metadata": {"remote_generation": "7"},
                        "derived_ms": {"actual_graph_wait_ms": 12.5},
                    },
                },
            }

        async def run():
            plan = build_execution_plan(
                {"1": {"class_type": "KSampler", "inputs": {"seed": 1}}},
                prompt_id="trace_merge",
                validate=False,
            )
            local_trace = RuntimeTrace(request_id="trace_merge", process="local")
            local_trace.emit("modal_submit_start")
            result = await execute_plan(
                plan,
                transport=ModalTransport(prompt_stream_fn=stream),
                trace=local_trace,
            )
            merged = result["trace"]
            event_names = {event["name"] for event in merged["events"]}
            self.assertIn("modal_submit_start", event_names)
            self.assertIn("container_entry", event_names)
            self.assertIn("sampler_end", event_names)
            self.assertEqual(merged["metadata"]["remote_generation"], "7")
            self.assertEqual(merged["derived_ms"]["actual_graph_wait_ms"], 12.5)

        asyncio.run(run())

    def test_event_trace_derives_stages_and_durations_without_fabrication(self):
        """V2 event traces gain only timing fields backed by real events."""
        async def stream(**kwargs):
            yield {
                "type": "result",
                "data": {
                    "outputs": {},
                    "trace": {
                        "events": [
                            {
                                "name": "container_entry",
                                "process": "remote",
                                "phase": "restore",
                                "wall_unix_ns": 1_000_000_000,
                                "monotonic_ns": 1_000_000_000,
                                "metadata": {},
                            },
                            {
                                "name": "sampler_start",
                                "process": "remote",
                                "phase": "execution",
                                "wall_unix_ns": 2_000_000_000,
                                "monotonic_ns": 2_000_000_000,
                                "metadata": {},
                            },
                            {
                                "name": "sampler_end",
                                "process": "remote",
                                "phase": "execution",
                                "wall_unix_ns": 3_000_000_000,
                                "monotonic_ns": 2_003_000_000,
                                "metadata": {},
                            },
                        ],
                        "metadata": {},
                    },
                },
            }

        async def run():
            plan = build_execution_plan(
                {"1": {"class_type": "KSampler", "inputs": {"seed": 1}}},
                prompt_id="event_timing",
                validate=False,
            )
            result = await execute_plan(
                plan,
                transport=ModalTransport(prompt_stream_fn=stream),
            )
            trace = result["trace"]
            self.assertEqual(trace["stages"]["t3_modal_entry"], 1.0)
            self.assertAlmostEqual(trace["deltas_ms"]["sampler"], 3.0)
            self.assertNotIn("vae_decode", trace["deltas_ms"])

        asyncio.run(run())

    def test_missing_profile_setter_is_safe_dry_run(self):
        """execute_plan with no profile_setter emits dry_run event and does not raise."""
        async def stream(**kwargs):
            yield {"type": "result", "data": {"images": [], "outputs": {}}}

        async def run():
            plan = build_execution_plan(
                {"1": {"class_type": "KSampler", "inputs": {"seed": 1}}},
                prompt_id="dry_run",
                validate=False,
            )
            trace = RuntimeTrace(request_id="dry_run", process="local")
            transport = ModalTransport(prompt_stream_fn=stream)
            result = await execute_plan(
                plan, transport=transport, trace=trace,
            )
            ev_names = [e.name for e in trace.events]
            self.assertIn("active_next_profile_end", ev_names)
            self.assertEqual(result["outputs"], {})
            self.assertIn("events", result["trace"])
        asyncio.run(run())

    def test_profile_setter_invoked_with_plan_workflow_and_hash(self):
        """When profile_setter is provided, prepare_active_next_profile is called
        with the plan's workflow and source_workflow_hash."""
        async def stream(**kwargs):
            yield {"type": "result", "data": {"images": [], "outputs": {}}}

        async def run():
            plan = build_execution_plan(
                {"1": {"class_type": "KSampler", "inputs": {"seed": 1}}},
                prompt_id="prof_test",
                validate=False,
            )
            setter = _FakeProfileSetter()
            transport = ModalTransport(prompt_stream_fn=stream)
            result = await execute_plan(
                plan, transport=transport, profile_setter=setter, workspace={"id": "ws1"},
            )
            self.assertEqual(len(setter.calls), 1)
            payload, ws = setter.calls[0]
            self.assertIn("workflow_hash", payload)
            # Profile result metadata should be in the result trace
            metadata = result.get("trace", {}).get("metadata", {})
            self.assertIn("active_profile_publish_decision", metadata)
        asyncio.run(run())

    def test_profile_setter_no_remote_no_cache_advance_when_not_provided(self):
        """Without profile_setter, no remote call occurs and metadata shows dry_run."""
        async def stream(**kwargs):
            yield {"type": "result", "data": {"images": [], "outputs": {}}}

        async def run():
            plan = build_execution_plan(
                {"1": {"class_type": "KSampler", "inputs": {"seed": 1}}},
                prompt_id="no_setter",
                validate=False,
            )
            transport = ModalTransport(prompt_stream_fn=stream)
            trace = RuntimeTrace(request_id="no_setter", process="local")
            result = await execute_plan(plan, transport=transport, trace=trace)
            metadata = result.get("trace", {}).get("metadata", {})
            # When setter is absent, dry_run emits events but no profile keys in metadata
            self.assertNotIn("active_profile_publish_decision", metadata)
        asyncio.run(run())

    def test_profile_setter_production_options_forwarded(self):
        """When the plan has an enabled production report, production options are
        forwarded to prepare_active_next_profile."""
        from canonical_execution import prompt_sha256

        async def stream(**kwargs):
            yield {"type": "result", "data": {"images": [], "outputs": {}}}

        async def run():
            wf = {"1": {"class_type": "KSampler", "inputs": {"seed": 1}}}
            actual_hash = prompt_sha256(wf)
            plan = build_execution_plan(
                wf,
                prompt_id="prod_prof",
                production_report={
                    "enabled": True,
                    "output_node_ids": ["9"],
                    "source_workflow_hash": "src_prod_hash",
                    "compiled_workflow_hash": actual_hash,
                },
                validate=False,
            )
            setter = _FakeProfileSetter()
            transport = ModalTransport(prompt_stream_fn=stream)
            await execute_plan(
                plan, transport=transport, profile_setter=setter, workspace={"id": "prod_ws"},
            )
            self.assertEqual(len(setter.calls), 1)
            payload, ws = setter.calls[0]
            # Production fields should be present in the activation payload
            self.assertEqual(payload.get("source_workflow_hash"), "src_prod_hash")
            self.assertEqual(payload.get("production_enabled"), True)
        asyncio.run(run())

    def test_profile_decision_timing_metadata_in_trace_metadata(self):
        """Profile decision and timing fields appear in the result trace metadata."""
        async def stream(**kwargs):
            yield {"type": "result", "data": {"images": [], "outputs": {}}}

        async def run():
            plan = build_execution_plan(
                {"1": {"class_type": "KSampler", "inputs": {"seed": 1}}},
                prompt_id="meta_test",
                validate=False,
            )
            setter = _FakeProfileSetter()
            transport = ModalTransport(prompt_stream_fn=stream)
            result = await execute_plan(
                plan, transport=transport, profile_setter=setter, workspace={"id": "ws"},
            )
            metadata = result.get("trace", {}).get("metadata", {})
            self.assertIn("active_profile_publish_decision", metadata)
            self.assertEqual(metadata["active_profile_publish_decision"], "published")
            self.assertIn("active_profile_stable_key", metadata)
            self.assertIn("local_active_profile_prepare_ms", metadata)
            self.assertIn("source_workflow_hash", metadata)
            # active_profile_prepare_count must be 1 when setter path is used
            self.assertEqual(metadata.get("active_profile_prepare_count"), 1)
            # These should be non-empty
            self.assertGreater(len(metadata["active_profile_stable_key"]), 0)
        asyncio.run(run())


# ═══════════════════════════════════════════════════════════════════════
# Local trace metadata merge — remote fields survive
# ═══════════════════════════════════════════════════════════════════════


class TestTraceMetadataMerge(unittest.TestCase):
    def test_local_events_and_metadata_merge_into_remote_trace(self):
        """Local RuntimeTrace events and metadata are merged into the remote
        result trace without discarding existing remote fields."""
        REMOTE_TRACE_FIELDS = {"stages": {"t3_modal_entry": 1000.0}, "backend_info": "xyz"}

        async def stream(**kwargs):
            yield {"type": "result", "data": {
                "images": [],
                "outputs": {},
                "trace": dict(REMOTE_TRACE_FIELDS),
            }}

        async def run():
            plan = build_execution_plan(
                {"1": {"class_type": "KSampler", "inputs": {"seed": 1}}},
                prompt_id="merge_test",
                validate=False,
            )
            setter = _FakeProfileSetter()
            transport = ModalTransport(prompt_stream_fn=stream)
            result = await execute_plan(
                plan, transport=transport, profile_setter=setter, workspace={"id": "ws"},
            )
            merged = result.get("trace", {})
            # Remote fields preserved
            self.assertEqual(merged.get("stages", {}).get("t3_modal_entry"),
                             REMOTE_TRACE_FIELDS["stages"]["t3_modal_entry"])
            # Legacy stages from local events merged alongside remote stages
            self.assertGreater(len(merged.get("stages", {})), 1,
                               "Legacy stages from local events must appear beside remote stages")
            self.assertEqual(merged.get("backend_info"), REMOTE_TRACE_FIELDS["backend_info"])
            # Local events present
            self.assertIn("events", merged)
            self.assertGreater(len(merged["events"]), 0)
            # Local metadata present
            self.assertIn("metadata", merged)
            self.assertIn("active_profile_publish_decision", merged["metadata"])
        asyncio.run(run())

    def test_local_events_not_present_when_remote_trace_absent(self):
        """When the remote trace is absent, execute_plan builds one from the
        local RuntimeTrace via to_legacy_timing, which includes both events and metadata."""
        async def stream(**kwargs):
            yield {"type": "result", "data": {"images": [], "outputs": {}}}

        async def run():
            plan = build_execution_plan(
                {"1": {"class_type": "KSampler", "inputs": {"seed": 1}}},
                prompt_id="no_remote_trace",
                validate=False,
            )
            setter = _FakeProfileSetter()
            transport = ModalTransport(prompt_stream_fn=stream)
            result = await execute_plan(
                plan, transport=transport, profile_setter=setter, workspace={"id": "ws"},
            )
            merged = result.get("trace", {})
            self.assertIn("events", merged)
            self.assertIn("metadata", merged)
            self.assertIn("stages", merged)
            self.assertIn("trace_version", merged)
        asyncio.run(run())

    def test_remote_trace_backend_preserved(self):
        """The backend field from the remote result is preserved in the merged trace."""
        async def stream(**kwargs):
            yield {"type": "result", "data": {
                "images": [],
                "outputs": {},
                "trace": {"stages": {"t3": 1.0}},
                "backend": {"container_id": "c123"},
            }}

        async def run():
            plan = build_execution_plan(
                {"1": {"class_type": "KSampler", "inputs": {"seed": 1}}},
                prompt_id="backend_test",
                validate=False,
            )
            transport = ModalTransport(prompt_stream_fn=stream)
            result = await execute_plan(plan, transport=transport)
            merged = result.get("trace", {})
            self.assertEqual(merged.get("backend"), {"container_id": "c123"})
        asyncio.run(run())

    def test_remote_metadata_missing_does_not_crash(self):
        """When remote trace exists but has no 'metadata' key, local metadata
        is still merged without error."""
        async def stream(**kwargs):
            yield {"type": "result", "data": {
                "images": [],
                "outputs": {},
                "trace": {"stages": {"t3": 1.0}},
            }}

        async def run():
            plan = build_execution_plan(
                {"1": {"class_type": "KSampler", "inputs": {"seed": 1}}},
                prompt_id="no_remote_md",
                validate=False,
            )
            setter = _FakeProfileSetter()
            transport = ModalTransport(prompt_stream_fn=stream)
            result = await execute_plan(
                plan, transport=transport, profile_setter=setter, workspace={"id": "ws"},
            )
            merged = result.get("trace", {})
            # Stages from remote preserved
            self.assertEqual(merged.get("stages", {}).get("t3"), 1.0)
            # Legacy stages from local events appear alongside remote stages
            self.assertGreater(len(merged.get("stages", {})), 1)
            # Local metadata merged successfully despite missing remote metadata
            self.assertIn("metadata", merged)
            self.assertIn("active_profile_publish_decision", merged["metadata"])
            # events still present
            self.assertIn("events", merged)
        asyncio.run(run())

    def test_remote_metadata_malformed_is_replaced(self):
        """When remote trace has a non-dict metadata field, it is replaced
        with a fresh dict so local metadata can be merged."""
        async def stream(**kwargs):
            yield {"type": "result", "data": {
                "images": [],
                "outputs": {},
                "trace": {"stages": {"t3": 1.0}, "metadata": "corrupt_string"},
            }}

        async def run():
            plan = build_execution_plan(
                {"1": {"class_type": "KSampler", "inputs": {"seed": 1}}},
                prompt_id="bad_remote_md",
                validate=False,
            )
            setter = _FakeProfileSetter()
            transport = ModalTransport(prompt_stream_fn=stream)
            result = await execute_plan(
                plan, transport=transport, profile_setter=setter, workspace={"id": "ws"},
            )
            merged = result.get("trace", {})
            # Stages from remote preserved
            self.assertEqual(merged.get("stages", {}).get("t3"), 1.0)
            # Legacy stages from local events merged alongside remote stages
            self.assertGreater(len(merged.get("stages", {})), 1)
            # metadata is now a dict with local fields (was a corrupt string)
            self.assertIsInstance(merged.get("metadata"), dict)
            self.assertIn("active_profile_publish_decision", merged["metadata"])
        asyncio.run(run())

    def test_backend_not_overwritten_when_result_has_no_backend(self):
        """When the result does not supply a 'backend' field, any existing
        remote trace 'backend' is preserved rather than replaced with {}."""
        async def stream(**kwargs):
            yield {"type": "result", "data": {
                "images": [],
                "outputs": {},
                "trace": {"stages": {"t3": 1.0}, "backend": {"original_container": "c1"}},
            }}

        async def run():
            plan = build_execution_plan(
                {"1": {"class_type": "KSampler", "inputs": {"seed": 1}}},
                prompt_id="backend_preserve",
                validate=False,
            )
            transport = ModalTransport(prompt_stream_fn=stream)
            result = await execute_plan(plan, transport=transport)
            merged = result.get("trace", {})
            # Backend from remote trace should be preserved
            self.assertEqual(merged.get("backend"), {"original_container": "c1"})
        asyncio.run(run())

    def test_backend_replaced_when_result_supplies_one(self):
        """When the result supplies a 'backend', it replaces the remote trace backend."""
        async def stream(**kwargs):
            yield {"type": "result", "data": {
                "images": [],
                "outputs": {},
                "trace": {"stages": {"t3": 1.0}, "backend": {"original": "old"}},
                "backend": {"new_container": "c2"},
            }}

        async def run():
            plan = build_execution_plan(
                {"1": {"class_type": "KSampler", "inputs": {"seed": 1}}},
                prompt_id="backend_replace",
                validate=False,
            )
            transport = ModalTransport(prompt_stream_fn=stream)
            result = await execute_plan(plan, transport=transport)
            merged = result.get("trace", {})
            # Result backend replaces trace backend
            self.assertEqual(merged.get("backend"), {"new_container": "c2"})
        asyncio.run(run())

    def test_profile_metadata_keys_in_trace_when_setter_provided(self):
        """When profile_setter is provided, the metadata block contains profile
        decision, stable key, token, and timing fields."""
        async def stream(**kwargs):
            yield {"type": "result", "data": {
                "images": [],
                "outputs": {},
                "trace": {"stages": {}},
            }}

        async def run():
            plan = build_execution_plan(
                {"1": {"class_type": "KSampler", "inputs": {"seed": 1}}},
                prompt_id="prof_meta",
                validate=False,
            )
            setter = _FakeProfileSetter()
            transport = ModalTransport(prompt_stream_fn=stream)
            result = await execute_plan(
                plan, transport=transport, profile_setter=setter, workspace={"id": "ws"},
            )
            md = result.get("trace", {}).get("metadata", {})
            expected_keys = {
                "active_profile_publish_decision",
                "active_profile_stable_key",
                "active_profile_token",
                "local_active_profile_prepare_ms",
                "active_profile_remote_call",
                "active_profile_remote_ms",
                "active_profile_prepare_count",
                "source_workflow_hash",
            }
            for key in expected_keys:
                self.assertIn(key, md, f"Expected metadata key '{key}' not found")
        asyncio.run(run())


# ═══════════════════════════════════════════════════════════════════════
# V2 plan path — restore publisher wiring (testable without ComfyUI)
# ═══════════════════════════════════════════════════════════════════════


class TestRestorePublisherWiring(unittest.TestCase):
    """Tests that execute_plan correctly wires restore_publisher into the
    restore publication flow and preserves no-op / generation semantics."""

    def setUp(self):
        _reset_restore_publish_cache()

    def test_restore_publisher_called_when_provided(self):
        """When restore_publisher is provided, it is called with a RestorePlan."""
        async def stream(**kwargs):
            yield {"type": "result", "data": {"images": [], "outputs": {}}}

        async def run():
            plan = build_execution_plan(
                {"1": {"class_type": "KSampler", "inputs": {"seed": 1}}},
                prompt_id="pub_test",
                validate=False,
            )
            publisher = _Publisher()
            transport = ModalTransport(prompt_stream_fn=stream)
            await execute_plan(plan, transport=transport, restore_publisher=publisher)
            self.assertEqual(len(publisher.plans), 1)
            self.assertIsInstance(publisher.plans[0], RestorePlan)
        asyncio.run(run())

    def test_restore_publisher_not_called_when_omitted(self):
        """When restore_publisher is None, no publication occurs and the event
        records not_configured."""
        async def stream(**kwargs):
            yield {"type": "result", "data": {"images": [], "outputs": {}}}

        async def run():
            plan = build_execution_plan(
                {"1": {"class_type": "KSampler", "inputs": {"seed": 1}}},
                prompt_id="no_pub",
                validate=False,
            )
            trace = RuntimeTrace(request_id="no_pub", process="local")
            transport = ModalTransport(prompt_stream_fn=stream)
            await execute_plan(plan, transport=transport, trace=trace)
            ev_meta = {e.name: dict(e.metadata) for e in trace.events}
            restore_end = ev_meta.get("restore_publish_end", {})
            self.assertEqual(restore_end.get("status"), "not_configured")
        asyncio.run(run())

    def test_publisher_generation_returned_in_event(self):
        """The generation returned by the publisher appears in the restore_publish_end event."""
        async def stream(**kwargs):
            yield {"type": "result", "data": {"images": [], "outputs": {}}}

        async def run():
            plan = build_execution_plan(
                {"1": {"class_type": "KSampler", "inputs": {"seed": 1}}},
                prompt_id="gen_test",
                validate=False,
            )
            publisher = _Publisher()
            transport = ModalTransport(prompt_stream_fn=stream)
            trace = RuntimeTrace(request_id="gen_test", process="local")
            await execute_plan(plan, transport=transport, restore_publisher=publisher, trace=trace)
            ev_meta = {e.name: dict(e.metadata) for e in trace.events}
            restore_end = ev_meta.get("restore_publish_end", {})
            self.assertEqual(restore_end.get("generation"), 1)
        asyncio.run(run())


# ═══════════════════════════════════════════════════════════════════════
# Restore-plan publish cache (local process-safe skip for unchanged
# canonical identity across workspace/app/environment)
# ═══════════════════════════════════════════════════════════════════════


class _FailPublisher:
    """Publisher that fails on configurable count, for failure-retry tests."""

    def __init__(self, fail_on: int = 1):
        self.call_count = 0
        self.plans = []
        self._fail_on = fail_on

    def publish(self, plan: RestorePlan) -> int:
        self.call_count += 1
        self.plans.append(plan)
        if self.call_count == self._fail_on:
            raise RuntimeError("publisher failure")
        return self.call_count


class _EnvVarOverride:
    """Context manager that temporarily sets os.environ values."""

    def __init__(self, **kwargs: str):
        self._overrides = kwargs
        self._originals: dict[str, str | None] = {}

    def __enter__(self):
        for key, value in self._overrides.items():
            self._originals[key] = os.environ.get(key)
            if value:
                os.environ[key] = value
            else:
                os.environ.pop(key, None)
        return self

    def __exit__(self, *args):
        for key, original in self._originals.items():
            if original is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = original


class TestRestorePublishCache(unittest.TestCase):
    """Local publish cache prevents redundant remote calls while preserving
    correctness for changed plans, different environments, and failures."""

    def setUp(self):
        _reset_restore_publish_cache()

    # ── helpers ──────────────────────────────────────────────────────────

    @staticmethod
    def _stream():
        async def _fn(**kwargs):
            yield {"type": "result", "data": {"images": [], "outputs": {}}}
        return _fn

    # ── first publish: cache miss → publisher called once ────────────────

    def test_first_publish_calls_publisher(self):
        """First execution with a plan calls the publisher exactly once."""
        async def run():
            plan = build_execution_plan(
                {"1": {"class_type": "KSampler", "inputs": {"seed": 1}}},
                prompt_id="first_pub", validate=False,
            )
            publisher = _Publisher()
            transport = ModalTransport(prompt_stream_fn=self._stream())
            await execute_plan(plan, transport=transport, restore_publisher=publisher)
            self.assertEqual(len(publisher.plans), 1,
                             "First publish must call publisher once")
        asyncio.run(run())

    # ── unchanged skip: same plan → second call skips publisher ──────────

    def test_unchanged_plan_skips_publisher(self):
        """Executing the same plan twice skips the publisher on the second call."""
        async def run():
            plan = build_execution_plan(
                {"1": {"class_type": "KSampler", "inputs": {"seed": 1}}},
                prompt_id="unchanged", validate=False,
            )
            publisher = _Publisher()
            transport = ModalTransport(prompt_stream_fn=self._stream())

            # First execution → cache miss → publish
            await execute_plan(plan, transport=transport, restore_publisher=publisher)
            self.assertEqual(len(publisher.plans), 1)

            # Second execution with same plan → cache hit → skip publish
            await execute_plan(plan, transport=transport, restore_publisher=publisher)
            self.assertEqual(len(publisher.plans), 1,
                             "Second call with same plan must NOT call publisher")
        asyncio.run(run())

    # ── changed republish: different plan → publisher called again ───────

    def test_changed_plan_republishes(self):
        """A different plan (changed workflow / model identity) calls the
        publisher again even after a previous plan was cached."""
        async def run():
            plan_a = build_execution_plan(
                {"1": {"class_type": "KSampler", "inputs": {"seed": 1}}},
                prompt_id="plan_a", validate=False,
            )
            plan_b = build_execution_plan(
                {"1": {"class_type": "KSampler", "inputs": {"seed": 999}}},
                prompt_id="plan_b", validate=False,
            )
            publisher = _Publisher()
            transport = ModalTransport(prompt_stream_fn=self._stream())

            await execute_plan(plan_a, transport=transport, restore_publisher=publisher)
            self.assertEqual(len(publisher.plans), 1, "plan_a must publish once")

            await execute_plan(plan_b, transport=transport, restore_publisher=publisher)
            self.assertEqual(len(publisher.plans), 2,
                             "plan_b (different identity) must publish again")
        asyncio.run(run())

    def test_changed_source_hash_republishes(self):
        """A different source_workflow_hash (same workflow) triggers a new
        publish because the identity hash includes source_workflow_hash."""
        async def run():
            base_wf = {"1": {"class_type": "KSampler", "inputs": {"seed": 1}}}
            plan_a = build_execution_plan(
                base_wf, prompt_id="hash_a", validate=False,
            )
            # Manually create a plan with a different source_workflow_hash
            plan_b = ExecutionPlan(
                workflow=base_wf,
                workflow_hash=plan_a.workflow_hash,
                source_workflow_hash="different_source_hash_001",
                execution_options=plan_a.execution_options,
                request_metadata={"prompt_id": "hash_b"},
            )
            publisher = _Publisher()
            transport = ModalTransport(prompt_stream_fn=self._stream())

            await execute_plan(plan_a, transport=transport, restore_publisher=publisher)
            self.assertEqual(len(publisher.plans), 1)

            await execute_plan(plan_b, transport=transport, restore_publisher=publisher)
            self.assertEqual(len(publisher.plans), 2,
                             "Different source_workflow_hash must republish")
        asyncio.run(run())

    def test_changed_model_identity_republishes(self):
        """A different model loader identity (e.g. different UNET) triggers
        a new publish."""
        async def run():
            plan_a = build_execution_plan(
                {"1": {"class_type": "UNETLoader", "inputs": {"unet_name": "model_a.safetensors"}},
                 "2": {"class_type": "KSampler", "inputs": {"seed": 1}}},
                prompt_id="model_a", validate=False,
            )
            plan_b = build_execution_plan(
                {"1": {"class_type": "UNETLoader", "inputs": {"unet_name": "model_b.safetensors"}},
                 "2": {"class_type": "KSampler", "inputs": {"seed": 1}}},
                prompt_id="model_b", validate=False,
            )
            publisher = _Publisher()
            transport = ModalTransport(prompt_stream_fn=self._stream())

            await execute_plan(plan_a, transport=transport, restore_publisher=publisher)
            self.assertEqual(len(publisher.plans), 1)

            await execute_plan(plan_b, transport=transport, restore_publisher=publisher)
            self.assertEqual(len(publisher.plans), 2,
                             "Different model identity must republish")
        asyncio.run(run())

    # ── workspace/environment isolation ──────────────────────────────────

    def test_different_workspace_isolation(self):
        """Same plan in a different workspace publishes again (cache key
        includes workspace_id)."""
        async def run():
            plan = build_execution_plan(
                {"1": {"class_type": "KSampler", "inputs": {"seed": 1}}},
                prompt_id="ws_test", validate=False,
            )
            publisher = _Publisher()
            transport = ModalTransport(prompt_stream_fn=self._stream())

            # Workspace A
            await execute_plan(
                plan, transport=transport, restore_publisher=publisher,
                workspace={"id": "workspace_a"},
            )
            self.assertEqual(len(publisher.plans), 1)

            # Same plan, different workspace → must publish again
            await execute_plan(
                plan, transport=transport, restore_publisher=publisher,
                workspace={"id": "workspace_b"},
            )
            self.assertEqual(len(publisher.plans), 2,
                             "Different workspace must re-publish")

            # Workspace A again → cache hit (it was cached from first call)
            await execute_plan(
                plan, transport=transport, restore_publisher=publisher,
                workspace={"id": "workspace_a"},
            )
            self.assertEqual(len(publisher.plans), 2,
                             "Back to workspace A must use cache (no publish)")
        asyncio.run(run())

    def test_different_environment_isolation(self):
        """Same plan in a different Modal environment publishes again."""
        async def run():
            plan = build_execution_plan(
                {"1": {"class_type": "KSampler", "inputs": {"seed": 1}}},
                prompt_id="env_test", validate=False,
            )
            publisher = _Publisher()
            transport = ModalTransport(prompt_stream_fn=self._stream())

            # Environment "staging"
            with _EnvVarOverride(COMFYMODAL_V2_ENVIRONMENT="staging"):
                await execute_plan(
                    plan, transport=transport, restore_publisher=publisher,
                )
                self.assertEqual(len(publisher.plans), 1)

            # Environment "production"
            with _EnvVarOverride(COMFYMODAL_V2_ENVIRONMENT="production"):
                await execute_plan(
                    plan, transport=transport, restore_publisher=publisher,
                )
                self.assertEqual(len(publisher.plans), 2,
                                 "Different environment must re-publish")

            # Environment "staging" again → cache hit
            with _EnvVarOverride(COMFYMODAL_V2_ENVIRONMENT="staging"):
                await execute_plan(
                    plan, transport=transport, restore_publisher=publisher,
                )
                self.assertEqual(len(publisher.plans), 2,
                                 "Back to staging must use cache")
        asyncio.run(run())

    def test_different_app_name_isolation(self):
        """Same plan under a different app name publishes again."""
        async def run():
            plan = build_execution_plan(
                {"1": {"class_type": "KSampler", "inputs": {"seed": 1}}},
                prompt_id="app_test", validate=False,
            )
            publisher = _Publisher()
            transport = ModalTransport(prompt_stream_fn=self._stream())

            with _EnvVarOverride(COMFYMODAL_V2_APP_NAME="app-shadow"):
                await execute_plan(
                    plan, transport=transport, restore_publisher=publisher,
                )
                self.assertEqual(len(publisher.plans), 1)

            with _EnvVarOverride(COMFYMODAL_V2_APP_NAME="app-prod"):
                await execute_plan(
                    plan, transport=transport, restore_publisher=publisher,
                )
                self.assertEqual(len(publisher.plans), 2,
                                 "Different app name must re-publish")
        asyncio.run(run())

    # ── failure does not poison cache ────────────────────────────────────

    def test_failed_publish_does_not_cache(self):
        """When the publisher raises, the cache is NOT populated, so a retry
        will call the publisher again."""
        async def run():
            plan = build_execution_plan(
                {"1": {"class_type": "KSampler", "inputs": {"seed": 1}}},
                prompt_id="fail_test", validate=False,
            )
            publisher = _FailPublisher(fail_on=1)
            transport = ModalTransport(prompt_stream_fn=self._stream())

            # First call fails → exception → no cache entry
            with self.assertRaises(RuntimeError):
                await execute_plan(
                    plan, transport=transport, restore_publisher=publisher,
                )
            self.assertEqual(publisher.call_count, 1,
                             "Publisher must have been called once")

            # Retry with a fresh publisher (same plan) — must NOT be skipped
            publisher2 = _Publisher()
            await execute_plan(
                plan, transport=transport, restore_publisher=publisher2,
            )
            self.assertEqual(len(publisher2.plans), 1,
                             "Retry after failure must call publisher again")
        asyncio.run(run())

    def test_failure_then_success_then_skip(self):
        """After a failure and a subsequent success, the cache is populated
        and a third call skips."""
        async def run():
            plan = build_execution_plan(
                {"1": {"class_type": "KSampler", "inputs": {"seed": 1}}},
                prompt_id="fail_success_test", validate=False,
            )
            transport = ModalTransport(prompt_stream_fn=self._stream())

            # First: fail on first call
            fail_pub = _FailPublisher(fail_on=1)
            with self.assertRaises(RuntimeError):
                await execute_plan(
                    plan, transport=transport, restore_publisher=fail_pub,
                )

            # Second: succeed (new publisher, cache miss → publish → cache)
            success_pub = _Publisher()
            await execute_plan(
                plan, transport=transport, restore_publisher=success_pub,
            )
            self.assertEqual(len(success_pub.plans), 1)

            # Third: same plan → cache hit → skip
            skip_pub = _Publisher()
            await execute_plan(
                plan, transport=transport, restore_publisher=skip_pub,
            )
            self.assertEqual(len(skip_pub.plans), 0,
                             "Third call with cached plan must skip publisher")
        asyncio.run(run())


# ═══════════════════════════════════════════════════════════════════════
# Derived-metrics fallback (replicates __init__._execute_job logic)
# ═══════════════════════════════════════════════════════════════════════


def _derive_active_next_metrics(result_trace: dict) -> dict:
    """Extract active-next metrics from a result trace dict using the same
    legacy-first / v2-fallback logic as _execute_job's post-materialization
    block.  Returns a ``derived_ms``-style dict."""
    derived: dict = {}
    _run_trace_summary = result_trace.get("_run_trace", {}) if isinstance(result_trace, dict) else {}
    _rt_counts = _run_trace_summary.get("counts", {}) if isinstance(_run_trace_summary, dict) else {}
    _rt_spans = _run_trace_summary.get("spans", {}) if isinstance(_run_trace_summary, dict) else {}
    _v2_meta = result_trace.get("metadata", {}) if isinstance(result_trace, dict) else {}
    if not isinstance(_v2_meta, dict):
        _v2_meta = {}

    _profile_span = _rt_spans.get("prepare_active_next_profile", {}) if isinstance(_rt_spans, dict) else {}
    if _profile_span and isinstance(_profile_span, dict) and _profile_span.get("called"):
        derived["active_profile_build_ms"] = _profile_span.get("duration_ms", 0)
    else:
        _v2_prepare_ms = _v2_meta.get("local_active_profile_prepare_ms", 0.0)
        derived["active_profile_build_ms"] = max(0.0, _v2_prepare_ms) if isinstance(_v2_prepare_ms, (int, float)) else 0.0
    if "active_profile_prepare_count" in _rt_counts:
        derived["active_profile_remote_call"] = _rt_counts.get("active_profile_prepare_count", 0)
    else:
        _v2_remote_call = _v2_meta.get("active_profile_prepare_count", 0)
        if isinstance(_v2_remote_call, (int, float)):
            derived["active_profile_remote_call"] = int(_v2_remote_call) if _v2_remote_call else 0
        else:
            derived["active_profile_remote_call"] = 1 if _v2_remote_call else 0
    derived["active_profile_to_gpu_submit_ms"] = 0.0
    return derived


class TestDerivedMetricsFallback(unittest.TestCase):
    """Legacy RunTrace spans take priority; v2 metadata fills in when absent."""

    def test_legacy_span_takes_priority(self):
        """When _run_trace has a called prepare_active_next_profile span, its
        duration_ms is used even when v2 metadata is also present."""
        trace = {
            "_run_trace": {
                "spans": {
                    "prepare_active_next_profile": {"called": True, "duration_ms": 42.5, "count": 1},
                },
                "counts": {"active_profile_prepare_count": 1},
            },
            "metadata": {
                "local_active_profile_prepare_ms": 3.0,
                "active_profile_prepare_count": 99,
            },
        }
        derived = _derive_active_next_metrics(trace)
        self.assertEqual(derived["active_profile_build_ms"], 42.5,
                         "Legacy span must take priority over v2 metadata")
        self.assertEqual(derived["active_profile_remote_call"], 1,
                         "Legacy count must take priority over v2 metadata")

    def test_v2_metadata_fallback_when_legacy_absent(self):
        """When no _run_trace envelope exists, v2 metadata fields are used."""
        trace = {
            "metadata": {
                "local_active_profile_prepare_ms": 12.7,
                "active_profile_prepare_count": 1,
            },
        }
        derived = _derive_active_next_metrics(trace)
        self.assertEqual(derived["active_profile_build_ms"], 12.7)
        self.assertEqual(derived["active_profile_remote_call"], 1)

    def test_v2_metadata_zero_prepare_ms_uses_zero(self):
        """When local_active_profile_prepare_ms is 0 or missing, build_ms is 0."""
        trace = {"metadata": {}}
        derived = _derive_active_next_metrics(trace)
        self.assertEqual(derived["active_profile_build_ms"], 0.0)

    def test_v2_metadata_negative_prepare_ms_clamped_to_zero(self):
        """A negative local_active_profile_prepare_ms is clamped to 0."""
        trace = {"metadata": {"local_active_profile_prepare_ms": -1.0}}
        derived = _derive_active_next_metrics(trace)
        self.assertEqual(derived["active_profile_build_ms"], 0.0)

    def test_v2_metadata_missing_prepare_count_defaults_zero(self):
        """When active_profile_prepare_count is absent, remote_call is 0."""
        trace = {"metadata": {}}
        derived = _derive_active_next_metrics(trace)
        self.assertEqual(derived["active_profile_remote_call"], 0)

    def test_v2_metadata_prepare_count_string_coerced_via_truthy(self):
        """A non-numeric truthy prepare_count is accepted as 1 (truthy path)."""
        trace = {"metadata": {"active_profile_prepare_count": "yes"}}
        derived = _derive_active_next_metrics(trace)
        self.assertEqual(derived["active_profile_remote_call"], 1)

    def test_v2_metadata_prepare_count_zero_explicit(self):
        """Zero prepare_count produces 0 remote_call."""
        trace = {"metadata": {"active_profile_prepare_count": 0}}
        derived = _derive_active_next_metrics(trace)
        self.assertEqual(derived["active_profile_remote_call"], 0)

    def test_none_trace_safe(self):
        """When trace is None or missing, all fall back to zero defaults."""
        derived = _derive_active_next_metrics({})
        self.assertEqual(derived["active_profile_build_ms"], 0.0)
        self.assertEqual(derived["active_profile_remote_call"], 0)

    def test_none_metadata_safe(self):
        """When trace.metadata is None, fallback does not crash."""
        trace = {"metadata": None}
        derived = _derive_active_next_metrics(trace)
        self.assertEqual(derived["active_profile_build_ms"], 0.0)
        self.assertEqual(derived["active_profile_remote_call"], 0)

    def test_malformed_metadata_replaced(self):
        """When trace.metadata is a non-dict (e.g. string), it is treated as
        empty — no crash and zero defaults."""
        trace = {"metadata": "corrupt"}
        derived = _derive_active_next_metrics(trace)
        self.assertEqual(derived["active_profile_build_ms"], 0.0)
        self.assertEqual(derived["active_profile_remote_call"], 0)

    def test_legacy_uncalled_span_falls_back_to_v2(self):
        """A legacy span present but not called (called=False) falls through
        to the v2 metadata path."""
        trace = {
            "_run_trace": {
                "spans": {
                    "prepare_active_next_profile": {"called": False, "duration_ms": 10.0, "count": 0},
                },
            },
            "metadata": {"local_active_profile_prepare_ms": 7.5},
        }
        derived = _derive_active_next_metrics(trace)
        # Span says called=False → falls through to v2 metadata
        self.assertEqual(derived["active_profile_build_ms"], 7.5)

    def test_legacy_count_absent_falls_back_to_v2(self):
        """When legacy counts lack active_profile_prepare_count, v2 metadata
        active_profile_prepare_count is used."""
        trace = {
            "_run_trace": {
                "spans": {},
                "counts": {"other_count": 5},
            },
            "metadata": {"active_profile_prepare_count": 2},
        }
        derived = _derive_active_next_metrics(trace)
        self.assertEqual(derived["active_profile_remote_call"], 2)


# ═══════════════════════════════════════════════════════════════════════
# Local trace-preservation tests (_execute_job mimic, V2 V2 trace merge)
# ═══════════════════════════════════════════════════════════════════════


class TestLocalV2TracePreservation(unittest.TestCase):
    """Prove V2 trace evidence survives the final local merge performed by
    ``__init__._execute_job`` after ``execute_plan`` returns.

    The pathological pattern:
        _merged_trace = trace.summary()            # legacy dict w/o events/metadata
        merge_remote_trace_into(_merged_trace, _remote_full)
        result["trace"] = _merged_trace            # overwrites rich remote trace

    These tests verify the fix that re-populates events, metadata, identity
    fields, and ``_restore_timing`` before the final assignment, and that
    empty local placeholders cannot overwrite authoritative remote values.
    """

    # ── helper: simulate the __init__._execute_job merge pattern ──────────

    @staticmethod
    def _simulate_execute_job_merge(
        local_legacy_trace: Any,
        remote_trace: dict,
        v2_meta: dict | None = None,
        result_top: dict | None = None,
    ) -> dict:
        """Replicate ``__init__._execute_job`` trace processing:

        1. ``trace.summary()``
        2. ``merge_remote_trace_into``
        3. V2 field preservation + identity hoist (THE FIX)
        4. Return merged dict (before ``result['trace'] = ...``)
        """
        from timing_trace import Trace, merge_remote_trace_into

        if not isinstance(local_legacy_trace, Trace):
            local_legacy_trace = Trace(prompt_id="test")
            if isinstance(local_legacy_trace, dict):
                local_legacy_trace = Trace(prompt_id="test")
        merged = local_legacy_trace.summary()
        merge_remote_trace_into(merged, remote_trace)
        _remote_full = remote_trace
        _v2_meta = v2_meta if v2_meta is not None else remote_trace.get("metadata", {})

        # ── Preservation block (mirrors __init__.py fix) ──
        _remote_events = _remote_full.get("events")
        if isinstance(_remote_events, list):
            merged["events"] = list(_remote_events)
        _remote_md = _remote_full.get("metadata")
        if isinstance(_remote_md, dict):
            merged["metadata"] = dict(_remote_md)
        for _key in ("trace_id", "request_id"):
            _val = _remote_full.get(_key)
            if _val:
                merged[_key] = _val
        _csid = _remote_full.get("container_session_id")
        if _csid:
            merged["container_session_id"] = _csid
        _rt_restore = (result_top or {}).get("_restore_timing")
        if _rt_restore:
            merged["_restore_timing"] = _rt_restore

        _IDENTITY_HOIST_KEYS = (
            "container_task_id", "container_session_id", "image_id",
            "gpu", "cloud", "region", "modal_input_id",
            "workspace_id", "app_name", "class_name", "method_name",
        )
        for _hk in _IDENTITY_HOIST_KEYS:
            if _hk in merged:
                continue
            _remote_val = _remote_full.get(_hk)
            if not _remote_val and isinstance(_v2_meta, dict):
                _remote_val = _v2_meta.get(_hk)
            if _remote_val:
                merged[_hk] = _remote_val

        return merged

    # ── tests ─────────────────────────────────────────────────────────────

    def setUp(self):
        from timing_trace import Trace
        self.trace = Trace(prompt_id="preserve_test")
        self.trace.mark("t1_local_recv")
        self.trace.mark("t2_local_dispatch")
        # Rich remote trace simulating what execute_plan returns for V2
        self.remote_trace: dict = {
            "events": [
                {"name": "container_entry", "process": "remote",
                 "wall_unix_ns": 1_500_000_000, "monotonic_ns": 100_000_000,
                 "metadata": {}},
                {"name": "sampler_end", "process": "remote",
                 "wall_unix_ns": 3_000_000_000, "monotonic_ns": 800_000_000,
                 "metadata": {}},
            ],
            "metadata": {
                "remote_generation": "42",
                "container_task_id": "task-abc-789",
                "gpu": "rtx-pro-6000",
                "app_name": "stable-modal-comfy-v2-shadow",
            },
            "trace_id": "trace-remote-uuid-00112233",
            "request_id": "req-preserve-test",
            "container_session_id": "sess-remote-abc123",
            "stages": {"t3_modal_entry": 1500.0},
            "container_task_id": "task-abc-789",
            "image_id": "img-12345",
            "gpu": "rtx-pro-6000",
            "cloud": "aws",
            "region": "us-east-1",
            "class_name": "ModalRuntimeEntrypointV2",
            "method_name": "run_plan_stream",
            "workspace_id": "ws-007",
        }
        # metadata that the local _v2_trace would inject (including empty placeholder)
        self.v2_meta_with_empty_placeholder: dict = {
            "container_session_id": "",  # local placeholder
            "container_task_id": "",
            "image_id": "",
            "gpu": "",
            "cloud": "",
            "region": "",
            "workspace_id": "",
            "modal_input_id": "",
        }

    def test_events_survive_final_merge(self):
        """Events from the remote trace survive the summary → merge → assign pattern."""
        merged = self._simulate_execute_job_merge(
            self.trace, self.remote_trace, self.v2_meta_with_empty_placeholder,
        )
        self.assertIn("events", merged)
        event_names = {e["name"] for e in merged["events"]}
        self.assertIn("container_entry", event_names)
        self.assertIn("sampler_end", event_names)

    def test_metadata_survive_final_merge(self):
        """Metadata dict from the remote trace survives the merge."""
        merged = self._simulate_execute_job_merge(
            self.trace, self.remote_trace, self.v2_meta_with_empty_placeholder,
        )
        self.assertIn("metadata", merged)
        self.assertIsInstance(merged["metadata"], dict)
        self.assertEqual(merged["metadata"]["remote_generation"], "42")

    def test_trace_id_and_request_id_survive(self):
        """Top-level trace_id and request_id propagate from remote trace."""
        merged = self._simulate_execute_job_merge(
            self.trace, self.remote_trace, self.v2_meta_with_empty_placeholder,
        )
        self.assertEqual(merged.get("trace_id"), "trace-remote-uuid-00112233")
        self.assertEqual(merged.get("request_id"), "req-preserve-test")

    def test_container_session_id_remote_nonempty_wins_over_empty_placeholder(self):
        """Authoritative remote container_session_id is preserved even when
        the local metadata has an empty placeholder."""
        merged = self._simulate_execute_job_merge(
            self.trace, self.remote_trace, self.v2_meta_with_empty_placeholder,
        )
        # "sess-remote-abc123" is nonempty at remote trace top-level, should win
        self.assertEqual(merged.get("container_session_id"), "sess-remote-abc123")

    def test_empty_placeholder_does_not_overwrite_remote(self):
        """When remote trace has 'gpu' but local v2_meta has empty gpu, the
        nonempty remote value survives."""
        merged = self._simulate_execute_job_merge(
            self.trace, self.remote_trace, self.v2_meta_with_empty_placeholder,
        )
        self.assertEqual(merged.get("gpu"), "rtx-pro-6000")

    def test_cloud_and_region_hoisted_from_remote(self):
        """cloud and region are hoisted from remote trace top-level."""
        merged = self._simulate_execute_job_merge(
            self.trace, self.remote_trace, self.v2_meta_with_empty_placeholder,
        )
        self.assertEqual(merged.get("cloud"), "aws")
        self.assertEqual(merged.get("region"), "us-east-1")

    def test_identity_keys_hoisted_from_remote_top_level(self):
        """container_task_id, image_id, class_name, method_name are hoisted
        from remote trace top-level (preferred over metadata with empties)."""
        merged = self._simulate_execute_job_merge(
            self.trace, self.remote_trace, self.v2_meta_with_empty_placeholder,
        )
        self.assertEqual(merged.get("container_task_id"), "task-abc-789",
                         "container_task_id should hoist from remote trace")
        self.assertEqual(merged.get("image_id"), "img-12345")
        self.assertEqual(merged.get("class_name"), "ModalRuntimeEntrypointV2")
        self.assertEqual(merged.get("method_name"), "run_plan_stream")

    def test_workspace_id_hoisted_from_remote_top_level(self):
        """workspace_id is hoisted from remote trace top-level."""
        merged = self._simulate_execute_job_merge(
            self.trace, self.remote_trace, self.v2_meta_with_empty_placeholder,
        )
        self.assertEqual(merged.get("workspace_id"), "ws-007")

    def test_identity_hoisted_from_metadata_when_top_level_absent(self):
        """When remote trace lacks a top-level identity key but metadata has
        it, the metadata value is used."""
        remote_no_top = dict(self.remote_trace)
        # Remove top-level identity keys that overlap with metadata
        for k in ("container_task_id", "gpu", "app_name"):
            remote_no_top.pop(k, None)
        merged = self._simulate_execute_job_merge(
            self.trace, remote_no_top, self.remote_trace["metadata"],
        )
        self.assertEqual(merged.get("container_task_id"), "task-abc-789",
                         "Should fall back to remote metadata")
        self.assertEqual(merged.get("gpu"), "rtx-pro-6000")
        self.assertEqual(merged.get("app_name"), "stable-modal-comfy-v2-shadow")

    def test_restore_timing_preserved_in_final_trace(self):
        """When the result has _restore_timing at top level, it appears in
        the merged trace."""
        result_top = {"_restore_timing": {"total_restore_ms": 1234.5, "stage_counts": {"model": 3}}}
        merged = self._simulate_execute_job_merge(
            self.trace, self.remote_trace, self.v2_meta_with_empty_placeholder,
            result_top=result_top,
        )
        self.assertIn("_restore_timing", merged)
        self.assertEqual(merged["_restore_timing"]["total_restore_ms"], 1234.5)

    def test_restore_timing_absent_when_result_has_none(self):
        """When the result has no _restore_timing, the merged trace does not
        contain _restore_timing."""
        merged = self._simulate_execute_job_merge(
            self.trace, self.remote_trace, self.v2_meta_with_empty_placeholder,
        )
        self.assertNotIn("_restore_timing", merged)

    def test_events_not_overwritten_when_remote_has_no_events(self):
        """When remote trace lacks events, the merged trace has no events key
        (or empty list) — no crash."""
        remote_no_events = dict(self.remote_trace)
        remote_no_events.pop("events", None)
        merged = self._simulate_execute_job_merge(
            self.trace, remote_no_events, self.v2_meta_with_empty_placeholder,
        )
        # Should be absent or empty, not crash
        self.assertNotIn("events", merged)

    def test_metadata_not_overwritten_when_remote_has_no_metadata(self):
        """When remote trace lacks metadata, the merged trace has no metadata
        key — no crash."""
        remote_no_md = dict(self.remote_trace)
        remote_no_md.pop("metadata", None)
        merged = self._simulate_execute_job_merge(
            self.trace, remote_no_md, self.v2_meta_with_empty_placeholder,
        )
        self.assertNotIn("metadata", merged)

    def test_legacy_stages_still_present(self):
        """Existing legacy behavior: stages from merge_remote_trace_into are
        still in the final trace."""
        merged = self._simulate_execute_job_merge(
            self.trace, self.remote_trace, self.v2_meta_with_empty_placeholder,
        )
        self.assertIn("stages", merged)
        self.assertEqual(merged["stages"].get("t3_modal_entry"), 1500.0)
        self.assertIn("t1_local_recv", merged["stages"])

    def test_all_fields_survive_e2e_via_execute_plan(self):
        """End-to-end: actual execute_plan result, then apply the _execute_job
        merge pattern, verify no loss."""
        async def stream(**kwargs):
            yield {"type": "result", "data": {
                "outputs": {},
                "trace": {
                    "events": [
                        {"name": "container_entry", "process": "remote", "phase": "restore",
                         "wall_unix_ns": 1_000_000_000, "monotonic_ns": 1_000_000_000, "metadata": {}},
                        {"name": "sampler_end", "process": "remote", "phase": "execution",
                         "wall_unix_ns": 2_000_000_000, "monotonic_ns": 1_500_000_000, "metadata": {}},
                    ],
                    "metadata": {"remote_gen": "e2e-test"},
                    "trace_id": "e2e-trace-001",
                    "request_id": "e2e-req-001",
                    "container_session_id": "e2e-sess-001",
                    "stages": {"t3_modal_entry": 1000.0},
                    "container_task_id": "e2e-task-001",
                    "gpu": "rtx-pro-6000",
                },
            }}

        async def run():
            plan = build_execution_plan(
                {"1": {"class_type": "KSampler", "inputs": {"seed": 1}}},
                prompt_id="e2e_preserve",
                validate=False,
            )
            local_runtime_trace = RuntimeTrace(request_id="e2e_preserve", process="local")
            local_runtime_trace.emit("modal_submit_start")
            result = await execute_plan(
                plan,
                transport=ModalTransport(prompt_stream_fn=stream),
                trace=local_runtime_trace,
            )
            # Simulate _execute_job merge on top of execute_plan output
            from timing_trace import Trace
            local_legacy = Trace(prompt_id="e2e_preserve")
            remote_trace = result.get("trace", {})
            merged = self._simulate_execute_job_merge(
                local_legacy, remote_trace,
                remote_trace.get("metadata", {}),
                result_top=result,
            )
            # events survive
            self.assertIn("events", merged)
            self.assertIn("sampler_end", {e["name"] for e in merged["events"]})
            # metadata survives
            self.assertIn("metadata", merged)
            self.assertEqual(merged["metadata"]["remote_gen"], "e2e-test")
            # trace_id / request_id survive
            self.assertEqual(merged.get("trace_id"), "e2e-trace-001")
            self.assertEqual(merged.get("request_id"), "e2e-req-001")
            # container_session_id survives
            self.assertEqual(merged.get("container_session_id"), "e2e-sess-001")
            # identity fields hoisted from top-level
            self.assertEqual(merged.get("container_task_id"), "e2e-task-001")
            self.assertEqual(merged.get("gpu"), "rtx-pro-6000")
            # legacy stages still present
            self.assertIn("stages", merged)

        asyncio.run(run())

    def test_identity_field_hoisted_from_metadata_when_remote_trace_top_level_empty(self):
        """When remote trace top-level has empty string for an identity field
        but metadata has a nonempty value, the metadata value is used."""
        remote_with_empty_top = dict(self.remote_trace)
        remote_with_empty_top["gpu"] = ""  # empty at top level
        merged = self._simulate_execute_job_merge(
            self.trace, remote_with_empty_top, self.remote_trace["metadata"],
        )
        # Should fall back to metadata which has "rtx-pro-6000"
        self.assertEqual(merged.get("gpu"), "rtx-pro-6000")

    def test_modal_input_id_hoisted_when_present(self):
        """modal_input_id is hoisted when present in remote trace."""
        remote_with_input_id = dict(self.remote_trace)
        remote_with_input_id["modal_input_id"] = "modal-input-999"
        merged = self._simulate_execute_job_merge(
            self.trace, remote_with_input_id, self.v2_meta_with_empty_placeholder,
        )
        self.assertEqual(merged.get("modal_input_id"), "modal-input-999")


if __name__ == "__main__":
    unittest.main()
