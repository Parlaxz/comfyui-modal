"""Offline tests for the isolated History V2 replay core."""
from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from comfymodal_runtime.contracts import ExecutionOptions, ExecutionPlan
from history_v2_models import RunAttempt
from history_v2_replay import (
    OriginalDecision,
    ReplayCapabilityError,
    build_original_replay_plan,
    build_replay_dispatch,
    decide_original_action,
    load_replay_plan,
    prepare_original_replay,
    validate_original_retry,
    validate_replay_capability,
    validate_replay_delta,
)


class HistoryV2ReplayCoreTests(unittest.TestCase):
    def setUp(self) -> None:
        workflow = {
            "1": {
                "class_type": "KSampler",
                "inputs": {"seed": 0, "steps": 0, "cfg": 0.0},
            },
            "2": {
                "class_type": "LoadImage",
                "inputs": {"image": "reference.png"},
            },
            "7": {"class_type": "SaveImage", "inputs": {"images": ["1", 0]}},
        }
        options = ExecutionOptions(
            production_enabled=True,
            production_output_node_ids=("7",),
            output_conversion_options={"format": "webp", "quality": 70},
            result_route="history-v2",
            profiling_level="detailed",
            requested_backend="modal",
            cancellation_options={"grace_seconds": 0},
            progress_options={"events": False},
            compatibility_flags={"legacy_mode": False},
            legacy_passthrough={"future_option": {"enabled": True}},
        )
        self.plan = ExecutionPlan(
            schema_version=1,
            workflow=workflow,
            workflow_hash="executed-workflow-hash",
            source_workflow_hash="source-workflow-hash",
            production_report={"enabled": True, "output_node_ids": ["7"]},
            model_stack={"checkpoint": "frozen.safetensors", "clip": "clip.safetensors"},
            prompt_bundle={"prompt": "immutable prompt", "negative_prompt": "none"},
            output_node_ids=("7",),
            input_images={"reference.png": "base64:reference"},
            execution_options=options,
            request_metadata={
                "workflow_id": "wf_frozen",
                "workflow_version_id": "wv_frozen",
                "preset_id": "preset_frozen",
                "prompt_id": "preview-prompt",
                "studio_controls": {
                    "seed": 0,
                    "steps": 0,
                    "cfg": 0.0,
                    "enabled": False,
                    "custom_control": "preserved",
                },
            },
            validation={"schema_version": 1, "validated": True, "certificate": "proof"},
            deployment_identity={"app": "comfy", "revision": "deploy-1"},
        )
        self.raw_plan = self.plan.to_dict()
        self.snapshot = {
            "snapshot_id": "snap_single",
            "schema_version": 1,
            "workflow": copy.deepcopy(self.raw_plan["workflow"]),
            "workflow_hash": self.raw_plan["workflow_hash"],
            "workflow_version_id": "wv_frozen",
            "request": {
                "workflow_id": "wf_frozen",
                "workflow_version_id": "wv_frozen",
                "preset_id": "preset_frozen",
                "controls": {
                    "seed": 0,
                    "steps": 0,
                    "cfg": 0.0,
                    "enabled": False,
                    "custom_control": "preserved",
                },
                "workflow_hash": self.raw_plan["workflow_hash"],
                "source_workflow_hash": self.raw_plan["source_workflow_hash"],
            },
            "preset_snapshot": {
                "preset_id": "preset_frozen",
                "preset_name": "Frozen Preset",
                "merged_values": {"seed": 0, "steps": 0},
            },
            "generation_params": {
                "workflow_id": "wf_frozen",
                "workflow_version_id": "wv_frozen",
                "preset_id": "preset_frozen",
                "controls": {"seed": 0, "enabled": False},
            },
            "execution_plan": copy.deepcopy(self.raw_plan),
            "deployment_identity": copy.deepcopy(self.raw_plan["deployment_identity"]),
        }

    def test_valid_new_single_snapshot_is_replay_capable(self):
        capability = validate_replay_capability(self.snapshot)
        self.assertTrue(capability.capable)
        self.assertEqual(capability.reason, "")

    def test_valid_experiment_cell_uses_the_same_core(self):
        experiment_snapshot = copy.deepcopy(self.snapshot)
        experiment_snapshot["snapshot_id"] = "snap_cell"
        experiment_snapshot["request"] = {
            "experiment_id": "exp_1",
            "cell_id": "cell_1",
            "workflow_id": "wf_frozen",
            "workflow_version_id": "wv_frozen",
            "preset_id": "preset_frozen",
            "axis_values": {"seed": 0},
            "controls": {"seed": 0, "enabled": False},
            "merged_values": {"seed": 0},
        }
        preparation = prepare_original_replay(experiment_snapshot)
        self.assertTrue(preparation.capability.capable)
        self.assertIsNotNone(preparation.saved_plan)
        self.assertIsNotNone(preparation.original_plan)
        assert preparation.saved_plan is not None
        self.assertEqual(
            preparation.saved_plan.to_dict(),
            self.raw_plan,
        )

    def test_legacy_missing_plan_is_rejected_without_synthesis(self):
        legacy = copy.deepcopy(self.snapshot)
        legacy["execution_plan"] = {}
        result = validate_replay_capability(legacy)
        self.assertFalse(result.capable)
        self.assertEqual(result.reason, "missing_execution_plan")

    def test_missing_raw_hash_is_rejected_before_from_dict(self):
        incomplete = copy.deepcopy(self.snapshot)
        incomplete["execution_plan"].pop("workflow_hash")
        with mock.patch.object(ExecutionPlan, "from_dict", side_effect=AssertionError("called")):
            result = validate_replay_capability(incomplete)
        self.assertFalse(result.capable)
        self.assertEqual(result.reason, "missing_workflow_hash")

    def test_malformed_plan_is_rejected(self):
        malformed = copy.deepcopy(self.snapshot)
        malformed["execution_plan"]["workflow"] = []
        self.assertEqual(validate_replay_capability(malformed).reason, "missing_workflow")

    def test_round_trip_is_exact_and_does_not_mutate_saved_dict(self):
        saved = copy.deepcopy(self.snapshot)
        plan = load_replay_plan(saved)
        self.assertEqual(plan.to_dict(), self.raw_plan)
        self.assertEqual(saved["execution_plan"], self.raw_plan)
        self.assertEqual(plan.workflow_hash, self.plan.workflow_hash)
        self.assertEqual(plan.source_workflow_hash, self.plan.source_workflow_hash)

    def test_output_intent_copy_changes_only_approved_fields(self):
        original = build_original_replay_plan(
            self.plan,
            request_id="original-request",
            prompt_id="original-prompt",
        )
        self.assertEqual(
            original.execution_options.output_conversion_options,
            {"format": "original"},
        )
        delta = validate_replay_delta(self.plan, original)
        self.assertTrue(delta.allowed)
        self.assertTrue(
            any(
                path.startswith("execution_options.output_conversion_options")
                for path in delta.changed_paths
            )
        )
        self.assertIn("request_metadata.request_id", delta.changed_paths)
        self.assertIn("request_metadata.prompt_id", delta.changed_paths)

        changed_workflow = ExecutionPlan(
            **{
                **self.raw_plan,
                "workflow": {"changed": {"class_type": "KSampler"}},
            }
        )
        invalid_delta = validate_replay_delta(self.plan, changed_workflow)
        self.assertFalse(invalid_delta.allowed)
        self.assertTrue(any(path.startswith("workflow") for path in invalid_delta.unexpected_paths))

    def test_plan_fields_controls_and_identity_are_preserved(self):
        original = build_original_replay_plan(self.plan)
        self.assertEqual(original.workflow, self.plan.workflow)
        self.assertEqual(original.workflow_hash, self.plan.workflow_hash)
        self.assertEqual(original.source_workflow_hash, self.plan.source_workflow_hash)
        self.assertEqual(original.model_stack, self.plan.model_stack)
        self.assertEqual(original.input_images, self.plan.input_images)
        self.assertEqual(original.output_node_ids, self.plan.output_node_ids)
        self.assertEqual(original.prompt_bundle, self.plan.prompt_bundle)
        self.assertEqual(original.validation, self.plan.validation)
        self.assertEqual(original.deployment_identity, self.plan.deployment_identity)
        self.assertEqual(original.request_metadata["studio_controls"]["seed"], 0)
        self.assertFalse(original.request_metadata["studio_controls"]["enabled"])
        self.assertEqual(original.execution_options.result_route, "history-v2")
        self.assertEqual(original.execution_options.legacy_passthrough["future_option"], {"enabled": True})

    def test_mutating_snapshot_after_preparation_cannot_rewrite_plan(self):
        preparation = prepare_original_replay(self.snapshot)
        assert preparation.saved_plan is not None
        self.snapshot["request"]["preset_id"] = "mutable-current-preset"
        self.snapshot["workflow"]["1"]["inputs"]["seed"] = 999
        self.assertEqual(preparation.saved_plan.request_metadata["preset_id"], "preset_frozen")
        self.assertEqual(preparation.saved_plan.workflow["1"]["inputs"]["seed"], 0)

    def test_production_deployment_identity_is_required(self):
        missing = copy.deepcopy(self.snapshot)
        missing["execution_plan"]["deployment_identity"] = {}
        missing["deployment_identity"] = {}
        result = validate_replay_capability(missing)
        self.assertEqual(result.reason, "missing_deployment_identity")

    def test_duplicate_decisions(self):
        active_original = [
            {"run_id": "preview", "mode": "preview", "status": "completed", "created_at": "1"},
            {"run_id": "original-active", "mode": "original", "status": "running", "created_at": "2"},
        ]
        decision = decide_original_action(active_original)
        self.assertEqual(decision.decision, OriginalDecision.REUSE_ACTIVE.value)
        self.assertEqual(decision.attempt_id, "original-active")

        successful = [
            {"run_id": "original-old", "mode": "original", "status": "completed", "created_at": "1"},
            {"run_id": "original-new", "mode": "original", "status": "completed", "created_at": "2"},
        ]
        decision = decide_original_action(successful)
        self.assertEqual(decision.decision, OriginalDecision.REUSE_SUCCESSFUL.value)
        self.assertEqual(decision.attempt_id, "original-new")

        failed = [{"run_id": "original-failed", "mode": "original", "status": "failed", "created_at": "2"}]
        decision = decide_original_action(failed)
        self.assertEqual(decision.decision, OriginalDecision.RETRY_REQUIRED.value)
        self.assertEqual(decision.attempt_id, "original-failed")

        decision = decide_original_action(successful, explicit_rerender=True)
        self.assertEqual(decision.decision, OriginalDecision.CREATE.value)

        preview_active = [{"run_id": "preview", "mode": "preview", "status": "running", "created_at": "2"}]
        decision = decide_original_action(preview_active)
        self.assertEqual(decision.decision, OriginalDecision.BUSY.value)

    def test_failed_original_retry_preserves_mode_generation_and_snapshot(self):
        failed = RunAttempt(
            run_id="original-failed",
            generation_id="gen_1",
            mode="original",
            status="failed",
            created_at="2026-08-17T00:00:00+00:00",
        )
        retry = validate_original_retry(
            failed,
            generation_id="gen_1",
            snapshot_id="snap_1",
            retry_snapshot_id="snap_1",
            snapshot=self.snapshot,
            retry_snapshot=copy.deepcopy(self.snapshot),
        )
        self.assertTrue(retry.valid)
        self.assertEqual(retry.mode, "original")
        self.assertEqual(retry.generation_id, "gen_1")

    def test_dispatch_contract_contains_validated_original_plan_without_execution(self):
        dispatch = build_replay_dispatch(
            self.snapshot,
            generation_id="gen_1",
            attempt_id="run_original_1",
            snapshot_id="snap_single",
            request_id="req_original",
        )
        self.assertEqual(dispatch.mode, "original")
        self.assertEqual(dispatch.executor_name, "canonical_execution.execute_plan")
        self.assertEqual(dispatch.plan.execution_options.output_conversion_options, {"format": "original"})
        with self.assertRaises(ReplayCapabilityError):
            build_replay_dispatch(
                {**self.snapshot, "execution_plan": {}},
                generation_id="gen_1",
                attempt_id="run_original_2",
            )


if __name__ == "__main__":
    unittest.main()
