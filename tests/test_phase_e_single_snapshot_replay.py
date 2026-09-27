"""Focused Phase E3A tests for modern Single replay snapshots."""
from __future__ import annotations

import asyncio
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import studio_workflow_run as swr
from comfymodal_runtime.contracts import ExecutionOptions, ExecutionPlan
from comfymodal_runtime.playground_service import PlaygroundService
from history_v2_repository import HistoryV2Repository
from history_v2_store import HistoryV2Store
from history_v2_writer import HistoryV2ProductionWriter, _gen_id


class PhaseESingleSnapshotReplayTests(unittest.TestCase):
    def _plan(self) -> ExecutionPlan:
        workflow = {
            "3": {
                "class_type": "KSampler",
                "inputs": {"seed": 0, "steps": 20, "model": ["4", 0]},
            },
            "4": {
                "class_type": "CheckpointLoaderSimple",
                "inputs": {"ckpt_name": "frozen.safetensors"},
            },
            "7": {"class_type": "SaveImage", "inputs": {"images": ["3", 0]}},
        }
        options = ExecutionOptions(
            production_enabled=True,
            production_output_node_ids=("7",),
            output_conversion_options={"format": "webp", "quality": 91},
            result_route="history-v2",
            profiling_level="detailed",
            requested_backend="modal",
            cancellation_options={"grace_seconds": 0},
            progress_options={"events": False},
            compatibility_flags={"legacy_mode": False},
            legacy_passthrough={"future_option": {"enabled": True}},
        )
        return ExecutionPlan(
            schema_version=1,
            workflow=workflow,
            workflow_hash="executed-workflow-hash",
            source_workflow_hash="source-workflow-hash",
            production_report={"enabled": True, "output_node_ids": ["7"]},
            model_stack={"checkpoint": "frozen.safetensors", "clip": "clip.safetensors"},
            prompt_bundle={"prompt": "immutable prompt", "negative_prompt": "none"},
            output_node_ids=("7",),
            input_images={"reference": "sha256:reference"},
            execution_options=options,
            request_metadata={
                "workflow_id": "wf_single",
                "workflow_version_id": "wv_frozen",
                "preset_id": "preset_frozen",
                "workflow_name": "Frozen Workflow",
                "preset_name": "Frozen Preset",
                "workflow_hash": "executed-workflow-hash",
                "studio_controls": {
                    "seed": 0,
                    "steps": 0,
                    "cfg": 0.0,
                    "enabled": False,
                    "custom_control": "complete",
                },
                "request_origin": "studio-single",
            },
            validation={"validated": True, "proof": "certificate-1"},
            deployment_identity={"app": "comfy", "revision": "deploy-1"},
        )

    def _snapshot_meta(self, plan: ExecutionPlan) -> dict:
        meta = dict(plan.request_metadata)
        meta.update(
            swr._build_plan_replay_meta(
                plan,
                modal_options={"execution_mode": "v2", "output": {"quality": 91}},
            )
        )
        meta["requested_controls"] = dict(plan.prompt_bundle)
        meta["playground_run"] = True
        return meta

    def test_plan_observer_receives_the_exact_plan_without_modal(self):
        plan = self._plan()
        observed = []
        saved = []

        async def execute_plan(*args, **kwargs):
            return {"outputs": {"7": {}}}

        async def save_history(*args, **kwargs):
            saved.append(args[0])

        service = PlaygroundService(
            load_preset_fn=lambda *args: ({"id": "preset_frozen"}, {}, None),
            validate_fn=lambda *args: None,
            build_plan_fn=lambda *args, **kwargs: (plan, None),
            execute_plan_fn=execute_plan,
            materialize_fn=lambda *args, **kwargs: ["artifact.png"],
            save_history_fn=save_history,
            plan_observer_fn=observed.append,
        )

        result = asyncio.run(
            service.execute(
                preset_id="preset_frozen",
                feature_id="workflow",
                controls={"seed": 0},
                node_dir=".",
            )
        )

        self.assertEqual(result["status"], "ok")
        self.assertEqual(observed, [plan])
        self.assertEqual(saved, [plan])

    def test_new_single_persists_complete_plan_and_request(self):
        plan = self._plan()
        with tempfile.TemporaryDirectory() as root:
            writer = HistoryV2ProductionWriter(root)
            repo = HistoryV2Repository(
                HistoryV2Store(Path(root) / ".studio_history_v2" / "history_v2.db")
            )
            meta = self._snapshot_meta(plan)
            writer.record_run(
                run_id="single-replay-complete",
                kind="playground_run",
                status="completed",
                prompt_id="single-replay-complete",
                workflow_hash=plan.workflow_hash,
                meta=meta,
            )

            generation_id = _gen_id("single-replay-complete")
            detail = repo.get_generation(generation_id)
            self.assertIsNotNone(detail)
            snapshot = detail.request_snapshot
            self.assertIsNotNone(snapshot)
            self.assertEqual(detail.generation.workflow_version_id, "wv_frozen")
            self.assertEqual(detail.generation.preset_id, "preset_frozen")
            self.assertEqual(detail.generation.model_stack, [plan.to_dict()["model_stack"]])
            self.assertEqual(snapshot.workflow, plan.to_dict()["workflow"])
            self.assertEqual(snapshot.workflow_hash, plan.workflow_hash)
            self.assertEqual(snapshot.request["controls"]["seed"], 0)
            self.assertEqual(snapshot.request["controls"]["enabled"], False)
            self.assertEqual(snapshot.request["controls"]["custom_control"], "complete")
            self.assertEqual(snapshot.request["modal_options"]["output"]["quality"], 91)
            self.assertEqual(snapshot.deployment_identity, plan.to_dict()["deployment_identity"])
            self.assertEqual(snapshot.execution_plan, plan.to_dict())
            self.assertEqual(
                ExecutionPlan.from_dict(snapshot.execution_plan).to_dict(),
                plan.to_dict(),
            )
            self.assertEqual(snapshot.execution_plan["input_images"], plan.to_dict()["input_images"])
            self.assertEqual(
                snapshot.execution_plan["execution_options"],
                plan.to_dict()["execution_options"],
            )

            changed_meta = self._snapshot_meta(plan)
            changed_meta["request_json"]["controls"]["seed"] = 999
            changed_meta["workflow_json"]["3"]["inputs"]["seed"] = 999
            writer.update_run(
                "single-replay-complete",
                status="completed",
                meta=changed_meta,
            )
            unchanged = repo.get_generation(detail.generation.generation_id).request_snapshot
            self.assertEqual(unchanged.request["controls"]["seed"], 0)
            self.assertEqual(unchanged.workflow["3"]["inputs"]["seed"], 0)

    def test_legacy_incomplete_snapshot_is_not_synthesized(self):
        with tempfile.TemporaryDirectory() as root:
            writer = HistoryV2ProductionWriter(root)
            repo = HistoryV2Repository(
                HistoryV2Store(Path(root) / ".studio_history_v2" / "history_v2.db")
            )
            writer.record_run(
                run_id="legacy-incomplete",
                kind="studio_run",
                status="completed",
                prompt_id="legacy-incomplete",
                workflow_hash="legacy-hash",
                meta={"workflow_json": {"3": {"class_type": "KSampler"}}},
            )
            generation_id = _gen_id("legacy-incomplete")
            snapshot = repo.get_generation(generation_id).request_snapshot
            self.assertEqual(snapshot.execution_plan, {})
            self.assertEqual(snapshot.request, {})
            self.assertEqual(snapshot.deployment_identity, {})


if __name__ == "__main__":
    unittest.main()
