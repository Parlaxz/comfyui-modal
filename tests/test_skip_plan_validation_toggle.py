"""Plan-validation escape hatch: `skip_plan_validation` toggle.

Temporary triage for validation false negatives (e.g. frontend-only
Set/Get nodes). Fail-closed stays the default; skipping is strictly opt-in
via per-request modal_options, the persisted Studio setting, or env.
"""
from __future__ import annotations

import asyncio
import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import aiohttp.web  # noqa: F401 — ensures `aiohttp.web` exists for the route stub

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def _run(coro):
    return asyncio.run(coro)


class SkipPlanValidationConfigTests(unittest.TestCase):
    """GET/POST /comfymodal/config persistence for the toggle."""

    @classmethod
    def setUpClass(cls):
        from tests.test_routes_registered import _StubServer, _build_init_with_stub

        cls.stub = _StubServer()
        cls.init_mod = _build_init_with_stub(cls.stub)

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._settings_file = str(Path(self._tmp.name) / ".modal_settings.json")
        self._orig = self.init_mod._MODAL_SETTINGS_FILE
        self.init_mod._MODAL_SETTINGS_FILE = self._settings_file
        self.init_mod._modal_settings_cache = None
        self.addCleanup(self._teardown)

    def _teardown(self):
        self.init_mod._MODAL_SETTINGS_FILE = self._orig
        self.init_mod._modal_settings_cache = None
        self._tmp.cleanup()

    def _get(self):
        from tests.test_routes_registered import _handler_for

        return _handler_for(self.init_mod, "GET", "/comfymodal/config")

    def _post(self):
        from tests.test_routes_registered import _handler_for

        return _handler_for(self.init_mod, "POST", "/comfymodal/config")

    def _request(self, body=None):
        from tests.test_routes_registered import _MockRequest

        return _MockRequest(json_body=body if body is not None else {})

    def test_default_is_fail_closed(self):
        body = json.loads(_run(self._get()(self._request())).body)
        self.assertIs(body.get("skip_plan_validation"), False)

    def test_post_true_persists_and_get_reflects(self):
        post = _run(self._post()(self._request({"skip_plan_validation": True})))
        self.assertEqual(post.status, 200)
        body = json.loads(_run(self._get()(self._request())).body)
        self.assertIs(body.get("skip_plan_validation"), True)

    def test_post_non_bool_rejected(self):
        post = _run(self._post()(self._request({"skip_plan_validation": "yes"})))
        self.assertEqual(post.status, 400)
        body = json.loads(_run(self._get()(self._request())).body)
        self.assertIs(body.get("skip_plan_validation"), False)


class SkipPlanValidationWorkflowRunTests(unittest.TestCase):
    """`build_workflow_execution_plan` maps the opt-out to proof collection."""

    def _bundle(self):
        return {
            "status": "ok",
            "workflow": {"workflow_id": "wf_t", "name": "Toggle Workflow"},
            "version": {"workflow_version_id": "wv_t"},
            "mapping": {"output_node_id": "1", "entries": []},
            "executable_prompt": {"1": {"class_type": "SaveImage", "inputs": {}}},
            "control_schema": {},
            "defaults": {},
        }

    def _recording_build(self, captured):
        import canonical_execution

        real = canonical_execution.build_execution_plan

        def fake(*args, **kwargs):
            captured.update(kwargs)
            return SimpleNamespace(
                schema_version=1,
                workflow={},
                workflow_hash="h",
                source_workflow_hash="s",
                production_report={},
                model_stack={},
                prompt_bundle={},
                output_node_ids=("1",),
                input_images={},
                execution_options={},
                request_metadata={},
                validation={},
                deployment_identity={},
            )

        return mock.patch.object(canonical_execution, "build_execution_plan", fake)

    def _run_build(self, modal_options, captured):
        import studio_workflow_run as swr

        with self._recording_build(captured):
            plan, err = swr.build_workflow_execution_plan(
                self._bundle(), {}, modal_options=modal_options, comfyui_root=""
            )
        return plan, err

    def test_default_collects_proof(self):
        captured: dict = {}
        plan, err = self._run_build({"production": {"enabled": True}}, captured)
        self.assertIsNone(err)
        self.assertIsNotNone(plan)
        self.assertIs(captured.get("collect_validation_proof"), True)

    def test_skip_true_skips_proof_and_marks_meta(self):
        captured: dict = {}
        plan, err = self._run_build(
            {"production": {"enabled": True}, "skip_plan_validation": True},
            captured,
        )
        self.assertIsNone(err)
        self.assertIsNotNone(plan)
        self.assertIs(captured.get("collect_validation_proof"), False)
        self.assertIs(
            (plan.request_metadata or {}).get("plan_validation_skipped"), True
        )

    def test_skip_truthy_string_does_not_skip(self):
        captured: dict = {}
        plan, err = self._run_build(
            {"production": {"enabled": True}, "skip_plan_validation": "yes"},
            captured,
        )
        self.assertIsNone(err)
        self.assertIsNotNone(plan)
        self.assertIs(captured.get("collect_validation_proof"), True)


class SkipCustomNodeGateTests(unittest.TestCase):
    """`resolve_workflow_run_bundle` tolerates pack reasons only on opt-out."""

    def _service(self, reasons):
        state = {
            "runnable": not reasons,
            "status": "ready" if not reasons else "incomplete",
            "reasons": list(reasons),
        }

        class _State:
            def to_dict(self):
                return dict(state)

        return SimpleNamespace(
            get_workflow=lambda wid: {"workflow_id": wid, "name": "Gate Workflow"},
            get_version=lambda vid: {
                "workflow_version_id": vid,
                "executable_prompt": {"1": {"class_type": "SaveImage", "inputs": {}}},
            },
            derive_version_state=lambda vid: _State(),
            get_mapping=lambda vid: {"entries": [], "output_node_id": "1"},
        )

    def _bundle(self, reasons, **kwargs):
        import studio_workflow_run as swr
        from unittest.mock import patch

        with patch.object(swr, "_get_domain_service", return_value=self._service(reasons)):
            return swr.resolve_workflow_run_bundle("wf_g", "wv_g", "/nonexistent", **kwargs)

    def test_default_blocks_custom_node_reason(self):
        bundle = self._bundle(["required custom node 'ComfyUI-KJNodes' not installed"])
        self.assertEqual(bundle["status"], "error")
        self.assertEqual(bundle["error_code"], "WORKFLOW_VERSION_NOT_RUNNABLE")

    def test_skip_passes_and_marks_state(self):
        bundle = self._bundle(
            ["required custom node 'ComfyUI-KJNodes' not installed"],
            skip_custom_node_gate=True,
        )
        self.assertEqual(bundle["status"], "ok")
        state = bundle["state"]
        self.assertTrue(state.get("runnable"))
        self.assertIs(state.get("custom_node_gate_skipped"), True)
        self.assertEqual(
            state.get("skipped_reasons"),
            ["required custom node 'ComfyUI-KJNodes' not installed"],
        )
        self.assertEqual(state.get("reasons"), [])

    def test_skip_keeps_model_reasons_fail_closed(self):
        bundle = self._bundle(
            [
                "required custom node 'ComfyUI-KJNodes' not installed",
                "missing model 'flux2-vae.safetensors' (vae)",
            ],
            skip_custom_node_gate=True,
        )
        self.assertEqual(bundle["status"], "error")
        self.assertEqual(bundle["error_code"], "WORKFLOW_VERSION_NOT_RUNNABLE")

    def test_skip_gate_active_precedence(self):
        import studio_workflow_run as swr

        with tempfile.TemporaryDirectory() as tmp:
            self.assertFalse(swr._skip_gate_active(None, tmp))
            self.assertFalse(swr._skip_gate_active({}, tmp))
            self.assertTrue(swr._skip_gate_active({"skip_plan_validation": True}, tmp))
            self.assertFalse(swr._skip_gate_active({"skip_plan_validation": "yes"}, tmp))
            with open(Path(tmp) / ".modal_settings.json", "w", encoding="utf-8") as f:
                json.dump({"skip_plan_validation": True}, f)
            self.assertTrue(swr._skip_gate_active(None, tmp))

    def test_skip_gate_active_env(self):
        import os
        import studio_workflow_run as swr

        with tempfile.TemporaryDirectory() as tmp:
            os.environ["COMFYMODAL_SKIP_PLAN_VALIDATION"] = "1"
            try:
                self.assertTrue(swr._skip_gate_active(None, tmp))
            finally:
                del os.environ["COMFYMODAL_SKIP_PLAN_VALIDATION"]


class ExpandSetGetTests(unittest.TestCase):
    """`expand_frontend_set_get_nodes` mirrors canvas link conversion."""

    def _graph(self, nodes):
        return {"nodes": nodes, "links": []}

    def test_expands_and_rewires(self):
        prompt = {
            "1": {"class_type": "PrimitiveInt", "inputs": {"value": 14}},
            "2": {"class_type": "SetNode", "inputs": {"INT": ["1", 0]}},
            "3": {"class_type": "GetNode", "inputs": {}},
            "4": {"class_type": "SaveImage", "inputs": {"images": ["3", 0]}},
        }
        graph = self._graph([
            {"id": 2, "type": "SetNode", "widgets_values": ["steps"]},
            {"id": 3, "type": "GetNode", "widgets_values": ["steps"]},
        ])
        import studio_workflow_run as swr

        before = json.loads(json.dumps(prompt))
        out = swr.expand_frontend_set_get_nodes(prompt, graph)
        self.assertNotIn("error", out)
        self.assertEqual(out["expanded"], 2)
        self.assertEqual(prompt, before, "inputs never mutated")
        workflow = out["workflow"]
        self.assertNotIn("2", workflow)
        self.assertNotIn("3", workflow)
        self.assertEqual(workflow["4"]["inputs"]["images"], ["1", 0])

    def test_noop_without_virtual_nodes(self):
        import studio_workflow_run as swr

        prompt = {"1": {"class_type": "SaveImage", "inputs": {}}}
        out = swr.expand_frontend_set_get_nodes(prompt, None)
        self.assertEqual(out, {"workflow": prompt, "expanded": 0})

    def test_get_without_set_fails_closed(self):
        import studio_workflow_run as swr

        prompt = {"3": {"class_type": "GetNode", "inputs": {}}}
        graph = self._graph([{"id": 3, "type": "GetNode", "widgets_values": ["nope"]}])
        out = swr.expand_frontend_set_get_nodes(prompt, graph)
        self.assertIn("error", out)

    def test_ambiguous_set_fails_closed(self):
        import studio_workflow_run as swr

        prompt = {
            "1": {"class_type": "PrimitiveInt", "inputs": {"value": 1}},
            "2": {"class_type": "SetNode", "inputs": {"INT": ["1", 0]}},
            "5": {"class_type": "SetNode", "inputs": {"INT": ["1", 0]}},
            "3": {"class_type": "GetNode", "inputs": {}},
        }
        graph = self._graph([
            {"id": 2, "type": "SetNode", "widgets_values": ["x"]},
            {"id": 5, "type": "SetNode", "widgets_values": ["x"]},
            {"id": 3, "type": "GetNode", "widgets_values": ["x"]},
        ])
        out = swr.expand_frontend_set_get_nodes(prompt, graph)
        self.assertIn("error", out)

    def test_missing_graph_fails_closed(self):
        import studio_workflow_run as swr

        prompt = {"3": {"class_type": "GetNode", "inputs": {}}}
        out = swr.expand_frontend_set_get_nodes(prompt, None)
        self.assertIn("error", out)

    def test_real_ideogram_version_expands_cleanly(self):
        import studio_workflow_run as swr

        with open(REPO_ROOT / ".studio_workflow_versions.json", encoding="utf-8") as f:
            versions = json.load(f)
        version = next(
            v for v in versions
            if v.get("workflow_version_id") == "wv_bb90922971ed4b04"
        )
        out = swr.expand_frontend_set_get_nodes(
            version["executable_prompt"], version["graph_json"]
        )
        self.assertNotIn("error", out)
        workflow = out["workflow"]
        leftovers = [
            k for k, n in workflow.items()
            if isinstance(n, dict) and n.get("class_type") in ("SetNode", "GetNode")
        ]
        self.assertEqual(leftovers, [])
        for node_id, node in workflow.items():
            if not isinstance(node, dict):
                continue
            for value in (node.get("inputs") or {}).values():
                if isinstance(value, (list, tuple)) and len(value) >= 2:
                    self.assertIn(
                        str(value[0]), workflow,
                        f"dangling link {value} on node {node_id}",
                    )


class BypassNodesTests(unittest.TestCase):
    """`bypass_nodes_by_id` wires consumers to the bypassed node's source."""

    def test_rewires_and_drops(self):
        import studio_workflow_run as swr

        prompt = {
            "166": {"class_type": "UNETLoader", "inputs": {"unet_name": "m.safetensors"}},
            "268": {"class_type": "PatchFlashAttentionKJ", "inputs": {"model": ["166", 0]}},
            "306": {"class_type": "RSAnySwitch", "inputs": {"input_1": ["268", 0]}},
        }
        before = json.loads(json.dumps(prompt))
        out = swr.bypass_nodes_by_id(prompt, ["268"])
        self.assertNotIn("error", out)
        self.assertEqual(out["bypassed"], ["268"])
        self.assertEqual(prompt, before, "inputs never mutated")
        workflow = out["workflow"]
        self.assertNotIn("268", workflow)
        self.assertEqual(workflow["306"]["inputs"]["input_1"], ["166", 0])

    def test_empty_list_is_noop(self):
        import studio_workflow_run as swr

        prompt = {"1": {"class_type": "SaveImage", "inputs": {}}}
        out = swr.bypass_nodes_by_id(prompt, [])
        self.assertEqual(out["bypassed"], [])
        self.assertEqual(out["workflow"], prompt)

    def test_missing_target_fails_closed(self):
        import studio_workflow_run as swr

        out = swr.bypass_nodes_by_id({"1": {"class_type": "X", "inputs": {}}}, ["999"])
        self.assertIn("error", out)

    def test_sourceless_target_fails_closed(self):
        import studio_workflow_run as swr

        prompt = {"2": {"class_type": "SetNode", "inputs": {}}}
        out = swr.bypass_nodes_by_id(prompt, ["2"])
        self.assertIn("error", out)

    def test_multi_source_target_fails_closed(self):
        import studio_workflow_run as swr

        prompt = {
            "2": {"class_type": "X", "inputs": {"a": ["1", 0], "b": ["3", 0]}},
            "1": {"class_type": "Y", "inputs": {}},
            "3": {"class_type": "Z", "inputs": {}},
        }
        out = swr.bypass_nodes_by_id(prompt, ["2"])
        self.assertIn("error", out)

    def test_ids_from_options(self):
        import studio_workflow_run as swr

        self.assertEqual(swr._bypass_ids_from_options(None), [])
        self.assertEqual(swr._bypass_ids_from_options({}), [])
        self.assertEqual(swr._bypass_ids_from_options({"bypass_node_ids": "268"}), [])
        self.assertEqual(
            swr._bypass_ids_from_options({"bypass_node_ids": ["268", 306]}),
            ["268", "306"],
        )

    def test_real_ideogram_patch_bypasses(self):
        import studio_workflow_run as swr

        with open(REPO_ROOT / ".studio_workflow_versions.json", encoding="utf-8") as f:
            versions = json.load(f)
        version = next(
            v for v in versions
            if v.get("workflow_version_id") == "wv_bb90922971ed4b04"
        )
        expanded = swr.expand_frontend_set_get_nodes(
            version["executable_prompt"], version["graph_json"]
        )
        self.assertNotIn("error", expanded)
        out = swr.bypass_nodes_by_id(expanded["workflow"], ["268"])
        self.assertNotIn("error", out)
        workflow = out["workflow"]
        self.assertNotIn("268", workflow)
        self.assertEqual(workflow["306"]["inputs"]["input_1"], ["166", 0])
        leftovers = [
            k for k, n in workflow.items()
            if isinstance(n, dict)
            and n.get("class_type") in ("SetNode", "GetNode", "PatchFlashAttentionKJ")
        ]
        self.assertEqual(leftovers, [])


class BroadcastAnythingEverywhereTests(unittest.TestCase):
    """`apply_anything_everywhere_broadcast` mirrors canvas Queue wiring."""

    def _graph(self, nodes, links=None):
        return {"nodes": nodes, "links": links or []}

    def _ue_node(self, nid=9, linked=True):
        inputs = [
            {"name": "anything", "type": "MODEL", "link": 101 if linked else None},
            {"name": "anything11", "type": "CLIP", "link": 102 if linked else None},
        ]
        return {
            "id": nid, "type": "Anything Everywhere", "mode": 0,
            "inputs": inputs,
            "properties": {"ue_properties": {}},
        }

    def test_fills_unconnected_matching_inputs(self):
        import studio_workflow_run as swr

        prompt = {
            "1": {"class_type": "CLIPLoader", "inputs": {"clip_name": "m.safetensors"}},
            "2": {"class_type": "CLIPTextEncode", "inputs": {"text": "x", "clip": None}},
            "9": {"class_type": "Anything Everywhere",
                  "inputs": {"anything11": ["1", 0]}},
        }
        graph = self._graph(
            [
                self._ue_node(),
                {"id": 1, "type": "CLIPLoader", "mode": 0, "inputs": []},
                {"id": 2, "type": "CLIPTextEncode", "mode": 0,
                 "inputs": [{"name": "clip", "type": "CLIP", "link": None}]},
            ],
            [[102, 1, 0, 9, 1, "CLIP"]],
        )
        before = json.loads(json.dumps(prompt))
        out = swr.apply_anything_everywhere_broadcast(prompt, graph)
        self.assertNotIn("error", out)
        self.assertEqual(out["broadcast"], 1)
        self.assertEqual(prompt, before, "inputs never mutated")
        self.assertEqual(out["workflow"]["2"]["inputs"]["clip"], ["1", 0])
        self.assertIn("9", out["workflow"], "controller node stays")

    def test_noop_without_controller(self):
        import studio_workflow_run as swr

        prompt = {"2": {"class_type": "CLIPTextEncode", "inputs": {"clip": None}}}
        out = swr.apply_anything_everywhere_broadcast(prompt, self._graph([]))
        self.assertEqual(out["broadcast"], 0)
        self.assertEqual(out["workflow"], prompt)

    def test_never_clobbers_existing_links(self):
        import studio_workflow_run as swr

        prompt = {
            "1": {"class_type": "CLIPLoader", "inputs": {}},
            "7": {"class_type": "CLIPLoader", "inputs": {}},
            "2": {"class_type": "CLIPTextEncode",
                  "inputs": {"text": "x", "clip": ["7", 0]}},
            "9": {"class_type": "Anything Everywhere",
                  "inputs": {"anything11": ["1", 0]}},
        }
        graph = self._graph(
            [
                self._ue_node(),
                {"id": 2, "type": "CLIPTextEncode", "mode": 0,
                 "inputs": [{"name": "clip", "type": "CLIP", "link": None}]},
            ],
            [[102, 1, 0, 9, 1, "CLIP"]],
        )
        out = swr.apply_anything_everywhere_broadcast(prompt, graph)
        self.assertEqual(out["broadcast"], 0)
        self.assertEqual(out["workflow"]["2"]["inputs"]["clip"], ["7", 0])

    def test_widget_inputs_and_muted_nodes_untouched(self):
        import studio_workflow_run as swr

        prompt = {
            "1": {"class_type": "CLIPLoader", "inputs": {}},
            "2": {"class_type": "CLIPTextEncode",
                  "inputs": {"text": "x", "clip": None}},
            "3": {"class_type": "CLIPTextEncode",
                  "inputs": {"text": "y", "clip": None}},
            "9": {"class_type": "Anything Everywhere",
                  "inputs": {"anything11": ["1", 0]}},
        }
        graph = self._graph(
            [
                self._ue_node(),
                {"id": 1, "type": "CLIPLoader", "mode": 0, "inputs": []},
                {"id": 2, "type": "CLIPTextEncode", "mode": 0,
                 "inputs": [{"name": "clip", "type": "CLIP", "link": None,
                             "widget": {"name": "clip"}}]},
                {"id": 3, "type": "CLIPTextEncode", "mode": 4,
                 "inputs": [{"name": "clip", "type": "CLIP", "link": None}]},
            ],
            [[102, 1, 0, 9, 1, "CLIP"]],
        )
        out = swr.apply_anything_everywhere_broadcast(prompt, graph)
        self.assertEqual(out["broadcast"], 0)
        self.assertIsNone(out["workflow"]["2"]["inputs"]["clip"])
        self.assertIsNone(out["workflow"]["3"]["inputs"]["clip"])

    def test_tied_sources_leave_input_alone(self):
        import studio_workflow_run as swr

        prompt = {
            "1": {"class_type": "CLIPLoader", "inputs": {}},
            "4": {"class_type": "CLIPLoader", "inputs": {}},
            "2": {"class_type": "CLIPTextEncode",
                  "inputs": {"text": "x", "clip": None}},
            "9": {"class_type": "Anything Everywhere",
                  "inputs": {"anything11": ["1", 0]}},
            "10": {"class_type": "Anything Everywhere",
                   "inputs": {"anything11": ["4", 0]}},
        }
        graph = self._graph(
            [
                self._ue_node(nid=9),
                self._ue_node(nid=10),
                {"id": 1, "type": "CLIPLoader", "mode": 0, "inputs": []},
                {"id": 4, "type": "CLIPLoader", "mode": 0, "inputs": []},
                {"id": 2, "type": "CLIPTextEncode", "mode": 0,
                 "inputs": [{"name": "clip", "type": "CLIP", "link": None}]},
            ],
            [[102, 1, 0, 9, 1, "CLIP"], [103, 4, 0, 10, 1, "CLIP"]],
        )
        out = swr.apply_anything_everywhere_broadcast(prompt, graph)
        self.assertEqual(out["broadcast"], 0)
        self.assertIsNone(out["workflow"]["2"]["inputs"]["clip"])

    def test_real_ideogram_version_broadcasts(self):
        import studio_workflow_run as swr

        with open(REPO_ROOT / ".studio_workflow_versions.json", encoding="utf-8") as f:
            versions = json.load(f)
        version = next(
            v for v in versions
            if v.get("workflow_version_id") == "wv_bb90922971ed4b04"
        )
        out = swr.apply_anything_everywhere_broadcast(
            version["executable_prompt"], version["graph_json"]
        )
        self.assertNotIn("error", out)
        self.assertGreater(out["broadcast"], 0)
        workflow = out["workflow"]
        self.assertEqual(workflow["167"]["inputs"]["clip"], ["168", 0])
        self.assertEqual(workflow["266"]["inputs"]["clip"], ["168", 0])
        self.assertEqual(workflow["162"]["inputs"]["vae"], ["158", 0])
        # Linked values untouched; controller intact.
        self.assertEqual(workflow["236"]["inputs"], {"INT": ["235", 0]})
        self.assertIn("209", workflow)
        rerun = swr.apply_anything_everywhere_broadcast(
            workflow, version["graph_json"]
        )
        self.assertEqual(rerun["broadcast"], 0)
        self.assertEqual(rerun["workflow"], workflow)


if __name__ == "__main__":
    unittest.main()
