"""Focused tests for the v2 canonical plan boundary.

Covers:
- Profile setter invocation and metadata propagation
- Local trace metadata merge onto remote result trace
- V2 plan path restore publisher wiring
"""

from __future__ import annotations

import asyncio
import unittest
from unittest.mock import AsyncMock, MagicMock

from canonical_execution import build_execution_plan, execute_plan
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
            self.assertEqual(merged.get("stages"), REMOTE_TRACE_FIELDS["stages"])
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
            self.assertEqual(merged.get("stages"), {"t3": 1.0})
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
            self.assertEqual(merged.get("stages"), {"t3": 1.0})
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


if __name__ == "__main__":
    unittest.main()
