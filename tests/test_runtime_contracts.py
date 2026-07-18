"""Focused tests for the v2 contracts and unified trace."""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from comfymodal_runtime import (
    DeploymentIdentity,
    ExecutionOptions,
    ExecutionPlan,
    ModelRestoreKey,
    OutputStrategy,
    PrefillKey,
    RestorePlan,
    RuntimeTrace,
    TraceEvent,
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
        self.assertEqual(options.output_conversion_options["format"], "webp")
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


if __name__ == "__main__":
    unittest.main()
