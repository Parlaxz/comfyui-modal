"""Focused tests for the v2 contracts and unified trace."""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from comfymodal_runtime import (
    METADATA_RUNTIME_MODE,
    METADATA_WORKFLOW_HASH_PREFIX,
    METADATA_APP_NAME,
    METADATA_CLASS_NAME,
    METADATA_METHOD_NAME,
    METADATA_MODAL_INPUT_ID,
    METADATA_CONTAINER_TASK_ID,
    METADATA_CONTAINER_SESSION_ID,
    METADATA_IMAGE_ID,
    METADATA_GPU,
    METADATA_CLOUD,
    METADATA_REGION,
    METADATA_CPU,
    METADATA_MEMORY_MB,
    METADATA_SNAPSHOT_ENABLED,
    METADATA_GPU_SNAPSHOT_ENABLED,
    METADATA_RESTORE_PLAN_GENERATION,
    DeploymentIdentity,
    ExecutionOptions,
    ExecutionPlan,
    ModelRestoreKey,
    OutputStrategy,
    PrefillKey,
    RestorePlan,
    RuntimeTrace,
    TraceEvent,
    diagnosis_metadata,
    merge_runtime_traces,
    merge_traces,
    PROCESS_LOCAL,
    PROCESS_PUBLISHER,
    PROCESS_REMOTE_LIFECYCLE,
    PROCESS_REMOTE_METHOD,
)


class TestExecutionContracts(unittest.TestCase):
    def test_legacy_options_are_normalized_once(self):
        options = ExecutionOptions.from_legacy(
            {
                "production": {"enabled": True, "output_node_ids": ["12", "2", "12"]},
                "output_format": "webp",
                "runtime": {"backend": "safe"},
                "actual_load": {"enabled": True, "mode": "unet_vae_only"},
            }
        )
        self.assertEqual(options.production_output_node_ids, ("2", "12"))
        self.assertEqual(options.requested_backend, "safe")
        self.assertEqual(options.output_conversion_options["format"], "webp_lossy")
        self.assertEqual(options.to_legacy_dict()["actual_load"]["mode"], "unet_vae_only")

    def test_legacy_options_restore_output_format(self):
        options = ExecutionOptions.from_legacy({"output_format": "jpeg"})
        self.assertEqual(options.to_legacy_dict()["output_format"], "jpeg")

    def test_execution_plan_round_trip_and_immutability(self):
        plan = ExecutionPlan(
            workflow={"3": {"class_type": "KSampler"}},
            production_report={"enabled": True, "output_node_ids": ["3"]},
            execution_options=ExecutionOptions(production_output_node_ids=("3",)),
        )
        self.assertEqual(ExecutionPlan.from_dict(plan.to_dict()).to_dict(), plan.to_dict())
        with self.assertRaises(AttributeError):
            plan.workflow = {}  # type: ignore[misc]
        with self.assertRaises(TypeError):
            plan.workflow["4"] = {}  # type: ignore[index]

    def test_restore_identity_separates_model_and_prompt(self):
        model = ModelRestoreKey(unet_identity="u", clip_identity="c", vae_identity="v")
        first = PrefillKey(model_key=model, prompt_bundle_hash="prompt-a")
        second = PrefillKey(model_key=model, prompt_bundle_hash="prompt-b")
        self.assertEqual(first.model_key.stable_hash, second.model_key.stable_hash)
        self.assertNotEqual(first.stable_hash, second.stable_hash)

    def test_restore_plan_round_trip(self):
        model = ModelRestoreKey(unet_identity="u")
        plan = RestorePlan(
            generation=4,
            model_key=model,
            prefill_key=PrefillKey(model_key=model, prompt_bundle_hash="p"),
            model_spec={"unet": "u"},
            prefill_spec={"eligible": True},
            source_workflow_hash="workflow",
        )
        self.assertEqual(RestorePlan.from_dict(plan.to_dict()).to_dict(), plan.to_dict())

    def test_deployment_and_output_contracts_serialize(self):
        identity = DeploymentIdentity(runtime_hash="r", dependency_hash="d", custom_node_hash="c")
        strategy = OutputStrategy(name="direct", source="direct_sink", priority=1)
        self.assertEqual(identity.to_dict()["combined_hash"], identity.combined_hash)
        self.assertEqual(strategy.to_dict()["source"], "direct_sink")


class TestUnifiedTrace(unittest.TestCase):
    def test_trace_event_has_dual_clocks_and_legacy_serializer(self):
        trace = RuntimeTrace(request_id="request")
        trace.emit("local_request_received")
        trace.emit("remote_return_start")
        payload = trace.to_dict()
        event = TraceEvent.from_dict(payload["events"][0])
        self.assertEqual(event.request_id, "request")
        self.assertGreater(event.wall_unix_ns, 0)
        self.assertGreater(event.monotonic_ns, 0)
        legacy = trace.to_legacy_timing(prompt_id="prompt")
        self.assertEqual(legacy["prompt_id"], "prompt")
        self.assertIn("t1_local_recv", legacy["stages"])

    def test_reference_trace_is_readable(self):
        path = Path(__file__).parents[1] / "reference" / "runtime-migration" / "archive" / "_last_trace_result.json"
        payload = json.loads(path.read_text(encoding="utf-8"))
        trace = RuntimeTrace.from_legacy(payload)
        self.assertTrue(trace.events)
        self.assertIn("container_entry", {event.name for event in trace.events})
        self.assertIn("graph_execution_start", {event.name for event in trace.events})

    def test_merge_deduplicates_exact_duplicate_events(self):
        local = RuntimeTrace(request_id="r1")
        event = TraceEvent.now("plan_build_start", process=PROCESS_LOCAL, request_id="r1")
        local.extend([event, event])
        merged = merge_runtime_traces(local)
        names = [e.name for e in merged.events]
        self.assertEqual(names, ["plan_build_start"])

    def test_merge_keeps_different_process_events_with_same_name(self):
        local = RuntimeTrace(request_id="r1")
        remote = RuntimeTrace(request_id="r1")
        local.emit("plan_build_start", process=PROCESS_LOCAL)
        remote.emit("plan_build_start", process=PROCESS_REMOTE_METHOD)
        merged = merge_runtime_traces(local, remote)
        processes = {e.process for e in merged.events}
        self.assertEqual(processes, {PROCESS_LOCAL, PROCESS_REMOTE_METHOD})

    def test_merge_keeps_none_values_silently(self):
        local = RuntimeTrace(request_id="r1")
        local.emit("plan_build_start")
        merged = merge_runtime_traces(local, None)
        self.assertEqual(len(merged.events), 1)

    def test_merge_sorts_by_wall_time_only(self):
        local = RuntimeTrace(request_id="r1")
        later = RuntimeTrace(request_id="r1")
        local.emit("first_event", process=PROCESS_LOCAL)
        later.emit("later_event", process=PROCESS_REMOTE_METHOD)
        merged = merge_runtime_traces(local, later)
        self.assertEqual(merged.events[0].name, "first_event")
        self.assertEqual(merged.events[1].name, "later_event")

    def test_merge_traces_compatibility_alias(self):
        local = RuntimeTrace(request_id="r1")
        local.emit("plan_build_start")
        merged = merge_traces(local)
        self.assertEqual(len(merged.events), 1)
        self.assertEqual(merged.events[0].name, "plan_build_start")

    def test_process_constants_defined(self):
        self.assertEqual(PROCESS_LOCAL, "local")
        self.assertEqual(PROCESS_PUBLISHER, "publisher")
        self.assertEqual(PROCESS_REMOTE_LIFECYCLE, "remote_lifecycle")
        self.assertEqual(PROCESS_REMOTE_METHOD, "remote_method")

    def test_common_metadata_constants_are_non_empty_strings(self):
        for constant in [
            METADATA_RUNTIME_MODE,
            METADATA_WORKFLOW_HASH_PREFIX,
            METADATA_APP_NAME,
            METADATA_CLASS_NAME,
            METADATA_METHOD_NAME,
            METADATA_MODAL_INPUT_ID,
            METADATA_CONTAINER_TASK_ID,
            METADATA_CONTAINER_SESSION_ID,
            METADATA_IMAGE_ID,
            METADATA_GPU,
            METADATA_CLOUD,
            METADATA_REGION,
            METADATA_CPU,
            METADATA_MEMORY_MB,
            METADATA_SNAPSHOT_ENABLED,
            METADATA_GPU_SNAPSHOT_ENABLED,
            METADATA_RESTORE_PLAN_GENERATION,
        ]:
            self.assertIsInstance(constant, str)
            self.assertTrue(len(constant) > 0)

    def test_diagnosis_metadata_filters_none(self):
        result = diagnosis_metadata(
            app_name="myapp",
            gpu="A100",
            region=None,
            cloud="aws",
            cpu=None,
        )
        self.assertEqual(result, {"app_name": "myapp", "gpu": "A100", "cloud": "aws"})

    def test_diagnosis_metadata_empty_when_all_none(self):
        result = diagnosis_metadata(app_name=None, gpu=None)
        self.assertEqual(result, {})

    def test_merge_uses_wall_time_not_monotonic_for_cross_process(self):
        local = RuntimeTrace(request_id="r1")
        remote = RuntimeTrace(request_id="r1")
        e1 = TraceEvent("local_before", process=PROCESS_LOCAL, request_id="r1", wall_unix_ns=1000, monotonic_ns=9999)
        e2 = TraceEvent("remote_after", process=PROCESS_REMOTE_LIFECYCLE, request_id="r1", wall_unix_ns=2000, monotonic_ns=1)
        local.extend([e1])
        remote.extend([e2])
        merged = merge_runtime_traces(local, remote)
        self.assertEqual(merged.events[0].name, "local_before")
        self.assertEqual(merged.events[1].name, "remote_after")
        self.assertGreater(merged.events[1].wall_unix_ns, merged.events[0].wall_unix_ns)


if __name__ == "__main__":
    unittest.main()
