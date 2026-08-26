"""Focused tests for the deployment-identity preservation blocker in
``studio_workflow_run.build_workflow_execution_plan`` (production branch).

Covers the narrow reconstruction contract ONLY:

* the production branch preserves every unaffected canonical ``ExecutionPlan``
  field when it rebuilds the modern plan — at minimum ``validation`` and
  ``deployment_identity`` — verbatim (never fabricated or recomputed)
* canonical ``request_metadata`` keys (``prompt_id``, ``client_id``,
  ``selected_gpu``, ``workspace_id``, ``request_origin_info``, ...) survive the
  reconstruction while the modern studio metadata is overlaid on top
* ``prompt_bundle`` remains the intentional modern override
* ``to_dict`` / ``from_dict`` round-trip of a rebuilt plan is exact
* an absent canonical identity stays empty (never synthesized)
* Phase C CLIP-repair + workflow hash are unchanged by the reconstruction

Deterministic + fast: temp-dir ``WorkflowDomainService`` fixtures, a stubbed
``nodes`` registry (parent-ComfyUI ``nodes`` is never imported), and a
controllable canonical plan builder injected at the most local seam
(``canonical_execution.build_execution_plan``).  No Modal, no deploy, no
generation.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import types
import unittest
from collections.abc import Mapping
from contextlib import ExitStack
from pathlib import Path
from typing import Any
from unittest import mock


def _norm(value: Any) -> Any:
    """Normalize frozen-mapping/tuple shapes for structural comparison."""
    if isinstance(value, Mapping):
        return {k: _norm(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_norm(v) for v in value]
    return value

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import canonical_execution
import studio_workflow_run as swr
from comfymodal_runtime.contracts import ExecutionOptions, ExecutionPlan
from studio_domain import WorkflowDomainService, derive_mapping_candidates
from workflow_metadata import prompt_sha256

# A subset of node classes used by the txt2img / clip-repair fixtures, stubbed
# into ``sys.modules["nodes"]`` so ``compute_registry_fingerprint`` and the
# registry-proof builder never import the parent-ComfyUI ``nodes`` module.
_STUB_CLASSES = ("KSampler", "CLIPTextEncode", "CLIPLoader",
                 "EmptyLatentImage", "CheckpointLoaderSimple", "SaveImage")


class _StubNode:
    """Stand-in for a NODE_CLASS_MAPPINGS entry (like ``_DummyNode``)."""


def _stub_nodes(mappings: dict | None = None):
    """Context manager installing a fake ``nodes`` registry (restoring the
    previous ``sys.modules`` entry on exit, exactly like the plan-proof suite)."""
    from contextlib import contextmanager

    mod = types.ModuleType("nodes")
    setattr(mod, "NODE_CLASS_MAPPINGS", mappings if mappings is not None else {
        name: _StubNode for name in _STUB_CLASSES
    })

    @contextmanager
    def _inner():
        saved = sys.modules.get("nodes")
        sys.modules["nodes"] = mod
        try:
            yield
        finally:
            if saved is None:
                sys.modules.pop("nodes", None)
            else:
                sys.modules["nodes"] = saved

    return _inner()


# ── Fixtures (standalone copies of the house patterns from
#    test_workflow_run_integration.py) ──────────────────────────────────────


def make_capture(prompt_nodes: dict, graph_json=None) -> dict:
    return {
        "graph_json": graph_json or {"id": "g1", "nodes": []},
        "api_prompt_json": {"workflow": {}, "output": prompt_nodes},
    }


def txt2img_prompt(seed: int = 0, steps: int = 20, sampler: str = "euler") -> dict:
    return {
        "1": {"class_type": "CLIPTextEncode", "inputs": {"text": "hello world", "clip": ["4", 0]}},
        "2": {"class_type": "CLIPTextEncode", "inputs": {"text": "negative", "clip": ["4", 0]}},
        "3": {"class_type": "KSampler", "inputs": {
            "model": ["4", 0], "seed": seed, "steps": steps, "cfg": 7.0,
            "sampler_name": sampler, "scheduler": "normal",
            "positive": ["1", 0], "negative": ["2", 0], "latent_image": ["5", 0],
            "denoise": 1.0}},
        "4": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": "krea_model.safetensors"}},
        "5": {"class_type": "EmptyLatentImage", "inputs": {"width": 512, "height": 512, "batch_size": 1}},
        "6": {"class_type": "SaveImage", "inputs": {"images": ["3", 0]}},
    }


def clip_repair_prompt(seed: int = 0, steps: int = 20, sampler: str = "euler") -> dict:
    """Representative immutable version: unique CLIPLoader node 62 and two
    CLIPTextEncode nodes (67 positive, 169 negative) whose ``clip`` inputs are
    ABSENT (Phase C repair fixture)."""
    return {
        "3": {"class_type": "KSampler", "inputs": {
            "model": ["62", 0], "seed": seed, "steps": steps, "cfg": 7.0,
            "sampler_name": sampler, "scheduler": "normal",
            "positive": ["67", 0], "negative": ["169", 0], "latent_image": ["5", 0],
            "denoise": 1.0}},
        "5": {"class_type": "EmptyLatentImage", "inputs": {"width": 512, "height": 512, "batch_size": 1}},
        "6": {"class_type": "SaveImage", "inputs": {"images": ["3", 0]}},
        "62": {"class_type": "CLIPLoader", "inputs": {"clip_name": "qwen_3_4b.safetensors"}},
        "67": {"class_type": "CLIPTextEncode", "inputs": {"text": "hello world"}},
        "169": {"class_type": "CLIPTextEncode", "inputs": {"text": "negative"}},
    }


def fake_node_def(class_type: str):
    if class_type == "KSampler":
        return (
            {
                "model": ("MODEL",),
                "positive": ("CONDITIONING",),
                "negative": ("CONDITIONING",),
                "latent_image": ("LATENT",),
                "seed": ("INT", {"min": 0, "max": 281474976710655, "step": 1, "default": 0}),
                "steps": ("INT", {"min": 1, "max": 150, "step": 1, "default": 20}),
                "cfg": ("FLOAT", {"min": 0.0, "max": 30.0, "step": 0.5, "default": 7.0}),
                "sampler_name": (["euler", "dpmpp_2m"],),
                "scheduler": (["normal", "karras"],),
                "denoise": ("FLOAT", {"min": 0.0, "max": 1.0, "step": 0.01, "default": 1.0}),
            },
            {},
        )
    if class_type == "CLIPTextEncode":
        return ({"text": ("STRING", {"multiline": True}), "clip": ("CLIP",)}, {})
    if class_type == "EmptyLatentImage":
        return (
            {
                "width": ("INT", {"min": 16, "max": 8192, "step": 8}),
                "height": ("INT", {"min": 16, "max": 8192, "step": 8}),
                "batch_size": ("INT", {"min": 1, "max": 64}),
            },
            {},
        )
    if class_type == "CheckpointLoaderSimple":
        return ({"ckpt_name": (["krea_model.safetensors", "flux-dev.safetensors"],)}, {})
    if class_type == "CLIPLoader":
        return ({"clip_name": (["qwen_3_4b.safetensors", "clip_l.safetensors"],)}, {})
    if class_type == "SaveImage":
        return ({"images": ("IMAGE",), "filename_prefix": ("STRING", {"default": "ComfyUI"})}, {})
    return None


def default_values(prompt: dict | None = None) -> dict:
    prompt = prompt or txt2img_prompt()
    return {
        "positive_prompt": "hello world",
        "negative_prompt": "negative",
        "seed": prompt["3"]["inputs"]["seed"],
        "steps": prompt["3"]["inputs"]["steps"],
        "cfg": prompt["3"]["inputs"]["cfg"],
        "sampler": prompt["3"]["inputs"]["sampler_name"],
        "scheduler": prompt["3"]["inputs"]["scheduler"],
        "denoise": prompt["3"]["inputs"]["denoise"],
        "width": prompt["5"]["inputs"]["width"],
        "height": prompt["5"]["inputs"]["height"],
        "model": prompt["4"]["inputs"]["ckpt_name"],
    }


def clip_repair_values(prompt: dict | None = None) -> dict:
    prompt = prompt or clip_repair_prompt()
    return {
        "positive_prompt": prompt["67"]["inputs"]["text"],
        "negative_prompt": prompt["169"]["inputs"]["text"],
        "seed": prompt["3"]["inputs"]["seed"],
        "steps": prompt["3"]["inputs"]["steps"],
        "cfg": prompt["3"]["inputs"]["cfg"],
        "sampler": prompt["3"]["inputs"]["sampler_name"],
        "scheduler": prompt["3"]["inputs"]["scheduler"],
        "denoise": prompt["3"]["inputs"]["denoise"],
        "width": prompt["5"]["inputs"]["width"],
        "height": prompt["5"]["inputs"]["height"],
        "model": prompt["62"]["inputs"]["clip_name"],
    }


# A realistic non-empty validation proof payload (mirrors
# ``_collect_plan_validation_proof`` output shape).
_VALIDATION_PAYLOAD = {
    "schema_version": 1,
    "validated": True,
    "source": "host_validate_prompt",
    "outputs_to_execute": ["3", "6"],
    "node_errors": {"3": {"errors": []}},
    "validated_workflow_hash": "vwh_fixed_0000000000",
}

# A realistic non-empty nested deployment identity (mirrors
# ``_collect_plan_deployment_identity`` output shape).
_DEPLOYMENT_IDENTITY = {
    "schema_version": 1,
    "deployment_combined_hash": "dep_fake_1",
    "deployment_combined_hash_source": "metadata",
    "host_mirror_deployment_combined_hash": "",
    "custom_nodes_generation": "g_fake_1",
    "registry_fingerprint": "fp_" + "a" * 64,
    "registry_proof": {
        "schema_version": 1,
        "workflow_class_count": 2,
        "classes": ["KSampler", "SaveImage"],
        "identities": {"KSampler": "kanon_sampler", "SaveImage": "kanon_save"},
        "missing_host": [],
        "unresolved_identity": [],
        "complete": True,
    },
    "registry_proof_complete": True,
    "dependency_manifest_identity": "di_" + "b" * 64,
    "deployment_identity_frozen": False,
    "deployment_identity_fail_closed_reason": "",
    "complete": True,
}


class StudioWorkflowRunPlanIdentityTests(unittest.TestCase):
    """Behavior tests for the production-branch plan reconstruction identity
    preservation (studio_workflow_run.build_workflow_execution_plan)."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = str(Path(self._tmp.name))
        self.service = WorkflowDomainService(self.root)
        self.wf = self.service.create_workflow("Text2Img Workflow")
        self.version = self._capture_mapped(self.wf["workflow_id"])
        self.version_id = self.version["workflow_version_id"]
        self.preset = self.service.create_preset(
            self.version_id, "Preset A", values=default_values()
        )
        self.preset_id = self.preset["preset_id"]
        self.service.set_default_preset(self.wf["workflow_id"], self.preset_id)
        self.addCleanup(self._tmp.cleanup)

    def tearDown(self) -> None:
        # Never leak the deployment-hash env override between tests.
        os.environ.pop("COMFYMODAL_V2_DEPLOYMENT_COMBINED_HASH", None)

    # ── helpers ──────────────────────────────────────────────────────────

    def _capture_mapped(self, workflow_id: str, prompt: dict | None = None) -> dict:
        prompt = prompt or txt2img_prompt()
        version = self.service.create_version_from_capture(
            workflow_id, make_capture(prompt)
        )
        capture = make_capture(prompt)
        entries, output_node_id = derive_mapping_candidates(
            capture, node_def_provider=fake_node_def
        )
        self.service.set_mapping(
            version["workflow_version_id"],
            entries={role: e.to_dict() for role, e in entries.items()},
            output_node_id=output_node_id,
        )
        return version

    def _service_patcher(self):
        """Patch the module's domain-service factory to use the temp service
        (no dependency resolver -> deterministic runnable states)."""
        return mock.patch(
            "studio_workflow_run._get_domain_service",
            new=lambda node_dir: WorkflowDomainService(str(node_dir)),
        )

    def _bundle(self) -> dict:
        with self._service_patcher():
            return swr.resolve_workflow_run_bundle(
                self.wf["workflow_id"], self.version_id, self.preset_id, self.root
            )

    def _clip_repair_bundle(self) -> dict:
        wf = self.service.create_workflow("Clip Repair Workflow")
        version = self._capture_mapped(wf["workflow_id"], clip_repair_prompt())
        preset = self.service.create_preset(
            version["workflow_version_id"], "Preset C",
            values=clip_repair_values(),
        )
        self.service.set_default_preset(wf["workflow_id"], preset["preset_id"])
        with self._service_patcher():
            bundle = swr.resolve_workflow_run_bundle(
                wf["workflow_id"], version["workflow_version_id"],
                preset["preset_id"], self.root,
            )
        self.assertEqual(bundle["status"], "ok")
        return bundle

    def _merged_values(self, bundle: dict, overrides: dict | None = None) -> dict:
        merged = swr.merge_workflow_controls(
            bundle["preset"], overrides or {}, bundle["control_schema"]
        )
        self.assertEqual(merged["errors"], [])
        return merged["values"]

    def _recording_build(self):
        """Patch canonical build with a recording wrapper around the real one.

        The plan-carried validation proof collector is stubbed to a canned
        payload so the real builder runs headless (no ComfyUI ``execution``
        module) while still exercising the E7 proof-collection contract.
        Returns ``(patcher, captured)``; ``captured["canonical"]`` holds the
        canonical plan the real builder returned before reconstruction.
        """
        real_build = canonical_execution.build_execution_plan
        captured: dict = {}

        def recording_build(*args, **kwargs):
            plan = real_build(*args, **kwargs)
            captured["canonical"] = plan
            return plan

        stack = ExitStack()
        stack.enter_context(mock.patch(
            "canonical_execution.build_execution_plan", recording_build
        ))
        stack.enter_context(mock.patch.object(
            canonical_execution, "_collect_plan_validation_proof",
            return_value=dict(_VALIDATION_PAYLOAD),
        ))
        return (stack, captured)

    # ── 1. non-empty nested deployment_identity preserved (real canonical) ──

    def test_production_preserves_deployment_identity_and_canonical_meta(self):
        """The production rebuild keeps the canonical plan's non-empty nested
        deployment_identity verbatim and preserves canonical request_metadata
        keys (prompt_id/client_id/selected_gpu/workspace_id) under the studio
        metadata overlay."""
        bundle = self._bundle()
        values = self._merged_values(bundle)

        os.environ["COMFYMODAL_V2_DEPLOYMENT_COMBINED_HASH"] = "dep_prod_test"
        patcher, captured = self._recording_build()
        with self._service_patcher(), mock.patch.object(
            canonical_execution, "_read_baked_custom_node_manifest",
            return_value={"production_custom_node_generation": "g_prod_1",
                          "overall_dependency_hash": "odh_prod_1"},
        ), patcher, _stub_nodes():
            plan, err = swr.build_workflow_execution_plan(
                bundle, values,
                modal_options={"production": {"enabled": True}},
            )
        self.assertIsNone(err, f"production plan build failed: {err}")
        self.assertIsInstance(plan, ExecutionPlan)
        canonical = captured["canonical"]

        # Non-empty nested deployment_identity preserved VERBATIM.
        self.assertTrue(dict(plan.deployment_identity))
        self.assertEqual(dict(plan.deployment_identity), dict(canonical.deployment_identity))
        dep = dict(plan.deployment_identity)
        self.assertEqual(dep["deployment_combined_hash"], "dep_prod_test")
        self.assertEqual(dep["custom_nodes_generation"], "g_prod_1")
        self.assertTrue(dep["dependency_manifest_identity"], "dependency identity present")
        registry_proof = dep.get("registry_proof") or {}
        self.assertTrue(registry_proof.get("classes"), "nested registry proof present")

        # validation preserved verbatim (E7: the studio seam collects the
        # plan-carried validation proof; the stubbed host collector's payload
        # must flow through the reconstruction untouched).  The builder
        # re-stamps validated_workflow_hash / node_type_fingerprint from the
        # finalized dispatch workflow, so those two are asserted against the
        # plan itself.
        self.assertEqual(_norm(plan.validation), _norm(canonical.validation))
        val = _norm(plan.validation)
        self.assertEqual(val["validated"], True)
        self.assertEqual(val["schema_version"], 1)
        self.assertEqual(val["source"], "host_validate_prompt")
        self.assertEqual(val["outputs_to_execute"], ["3", "6"])
        self.assertEqual(val["node_errors"], {"3": {"errors": []}})
        self.assertEqual(val["validated_workflow_hash"], plan.workflow_hash)
        self.assertEqual(
            val["node_type_fingerprint"],
            sorted(
                node["class_type"]
                for node in swr._plain_copy(plan.workflow).values()
                if isinstance(node, dict)
            ),
        )

        # Every other unaffected canonical field preserved verbatim.
        self.assertEqual(plan.schema_version, canonical.schema_version)
        self.assertEqual(dict(plan.workflow), dict(canonical.workflow))
        self.assertEqual(plan.workflow_hash, canonical.workflow_hash)
        self.assertEqual(plan.source_workflow_hash, canonical.source_workflow_hash)
        self.assertEqual(dict(plan.production_report), dict(canonical.production_report))
        self.assertEqual(dict(plan.model_stack), dict(canonical.model_stack))
        self.assertEqual(plan.output_node_ids, canonical.output_node_ids)
        self.assertEqual(dict(plan.input_images), dict(canonical.input_images))
        self.assertEqual(
            plan.execution_options.to_dict(), canonical.execution_options.to_dict()
        )

        # request_metadata: canonical keys preserved, studio identity overlaid.
        canonical_meta = dict(canonical.request_metadata)
        meta = dict(plan.request_metadata)
        for canonical_key in ("prompt_id", "client_id", "selected_gpu", "workspace_id"):
            self.assertIn(canonical_key, meta)
            self.assertEqual(meta[canonical_key], canonical_meta[canonical_key])
        self.assertEqual(meta["workflow_id"], bundle["workflow"]["workflow_id"])
        self.assertEqual(
            meta["workflow_version_id"], bundle["version"]["workflow_version_id"]
        )
        self.assertEqual(meta["preset_id"], bundle["preset"]["preset_id"])
        self.assertEqual(meta["workflow_name"], bundle["workflow"]["name"])
        self.assertEqual(meta["preset_name"], bundle["preset"]["name"])
        self.assertEqual(meta["workflow_hash"], canonical_meta["workflow_hash"])
        # Modern identity: NO legacy studio keys are ever reintroduced.
        for legacy_key in ("studio_preset_id", "studio_snapshot_id", "studio_preset_label"):
            self.assertNotIn(legacy_key, meta)

    # ── 2. non-empty validation + all canonical fields preserved (fake) ──

    def test_production_preserves_validation_and_all_canonical_fields(self):
        """The production rebuild preserves a non-empty canonical validation
        proof and every unaffected field; only prompt_bundle is overridden
        (intentional) and request_metadata is a canonical+studio overlay."""
        bundle = self._bundle()
        values = self._merged_values(bundle)
        seen: dict = {}

        def fake_canonical_build(workflow, *, prompt_id="", client_id="",
                                 input_images=None, modal_options=None,
                                 production_options=None, production_report=None,
                                 gpu="", workspace=None, request_metadata=None,
                                 comfyui_root="", trace=None, validate=True,
                                 collect_validation_proof=False):
            seen["prompt_id"] = prompt_id
            seen["request_metadata"] = dict(request_metadata or {})
            return ExecutionPlan(
                workflow=workflow,
                workflow_hash=prompt_sha256(workflow),
                source_workflow_hash=prompt_sha256(workflow),
                production_report={"enabled": True, "output_node_ids": ["6"],
                                   "source_workflow_hash": prompt_sha256(workflow)},
                model_stack={"model": "krea_model.safetensors", "clip": []},
                prompt_bundle={"canonical_bundle_marker": True},
                output_node_ids=("6",),
                input_images={},
                execution_options=ExecutionOptions(
                    production_enabled=True,
                    production_output_node_ids=("6",),
                    result_route="studio_workflow",
                ),
                request_metadata={
                    **dict(request_metadata or {}),
                    "prompt_id": prompt_id or "canonical_pid",
                    "client_id": "canonical_cid",
                    "selected_gpu": gpu or "gpu_test",
                    "workspace_id": "ws_test",
                    "request_origin_info": {"origin": "studio_test", "lane": "workflow"},
                },
                validation=dict(_VALIDATION_PAYLOAD),
                deployment_identity=_DEPLOYMENT_IDENTITY,
            )

        with self._service_patcher(), mock.patch(
            "canonical_execution.build_execution_plan", fake_canonical_build
        ):
            plan, err = swr.build_workflow_execution_plan(
                bundle, values,
                modal_options={"production": {"enabled": True}},
                # H20 Wave G: the F8 GPU-freeze overlay stamps
                # request_metadata.selected_gpu from the builder's resolved gpu
                # argument (registered F8 tests pin this). Pass an explicit gpu
                # so the overlay and the canonical fake agree.
                gpu="gpu_test",
            )
        self.assertIsNone(err, f"production plan build failed: {err}")
        self.assertIsInstance(plan, ExecutionPlan)

        # Non-empty nested validation preserved verbatim (thawed serialization
        # matches the canned payload exactly).
        self.assertEqual(plan.to_dict()["validation"], _VALIDATION_PAYLOAD)

        # Non-empty nested deployment_identity preserved verbatim.
        self.assertEqual(plan.to_dict()["deployment_identity"], _DEPLOYMENT_IDENTITY)

        # Unaffected canonical fields preserved.
        self.assertEqual(plan.schema_version, 1)
        self.assertEqual(plan.workflow_hash, prompt_sha256(swr._plain_copy(plan.workflow)))
        self.assertTrue(plan.source_workflow_hash)
        self.assertEqual(plan.to_dict()["production_report"]["output_node_ids"], ["6"])
        self.assertEqual(dict(plan.model_stack)["model"], "krea_model.safetensors")
        self.assertEqual(plan.output_node_ids, ("6",))
        self.assertEqual(dict(plan.input_images), {})
        self.assertTrue(plan.execution_options.production_enabled)
        self.assertEqual(plan.execution_options.result_route, "studio_workflow")

        # prompt_bundle override is INTENTIONAL: the modern bundle wins.
        bundle_meta = dict(plan.prompt_bundle)
        self.assertNotIn("canonical_bundle_marker", bundle_meta)
        self.assertEqual(bundle_meta["prompt"], values.get("positive_prompt", ""))
        self.assertEqual(bundle_meta["negative_prompt"], values["negative_prompt"])
        for excluded in ("seed", "steps", "cfg", "sampler", "scheduler", "denoise"):
            self.assertNotIn(excluded, bundle_meta)

        # request_metadata overlay: canonical keys preserved + studio identity.
        meta = dict(plan.request_metadata)
        self.assertEqual(meta["prompt_id"], seen["prompt_id"], "canonical prompt_id kept")
        self.assertEqual(meta["client_id"], "canonical_cid")
        self.assertEqual(meta["selected_gpu"], "gpu_test")
        self.assertEqual(meta["workspace_id"], "ws_test")
        self.assertEqual(
            meta["request_origin_info"], {"origin": "studio_test", "lane": "workflow"}
        )
        self.assertEqual(meta["workflow_hash"], seen["request_metadata"]["workflow_hash"])
        self.assertEqual(meta["workflow_id"], bundle["workflow"]["workflow_id"])
        self.assertEqual(meta["studio_feature_id"], "workflow")
        for legacy_key in ("studio_preset_id", "studio_snapshot_id", "studio_preset_label"):
            self.assertNotIn(legacy_key, meta)

    # ── 3. to_dict/from_dict exact round-trip of a rebuilt plan ──────────

    def test_production_plan_to_dict_from_dict_round_trip_exact(self):
        """A rebuilt production plan (non-empty validation + deployment
        identity + overlaid request_metadata) survives to_dict -> from_dict
        exactly."""
        plan = self._build_rebuilt_production_plan_with_identity()
        self.assertTrue(dict(plan.validation))
        self.assertTrue(dict(plan.deployment_identity))

        serialized = plan.to_dict()
        restored = ExecutionPlan.from_dict(serialized)
        self.assertEqual(restored.to_dict(), serialized)
        self.assertEqual(dict(restored.validation), dict(plan.validation))
        self.assertEqual(
            dict(restored.deployment_identity), dict(plan.deployment_identity)
        )
        self.assertEqual(dict(restored.request_metadata), dict(plan.request_metadata))
        self.assertEqual(dict(restored.prompt_bundle), dict(plan.prompt_bundle))
        self.assertEqual(restored.workflow_hash, plan.workflow_hash)

    # ── 4. absent canonical identity stays empty ─────────────────────────

    def test_production_absent_identity_stays_empty(self):
        """A canonical plan carrying NO validation/deployment identity yields
        a rebuilt plan with the same empty identity (never fabricated)."""
        bundle = self._bundle()
        values = self._merged_values(bundle)

        def fake_canonical_build_empty(workflow, *, prompt_id="", client_id="",
                                       input_images=None, modal_options=None,
                                       production_options=None, production_report=None,
                                       gpu="", workspace=None, request_metadata=None,
                                       comfyui_root="", trace=None, validate=True,
                                       collect_validation_proof=False):
            return ExecutionPlan(
                workflow=workflow,
                workflow_hash=prompt_sha256(workflow),
                source_workflow_hash=prompt_sha256(workflow),
                production_report={"enabled": True, "output_node_ids": ["6"]},
                model_stack={},
                prompt_bundle={},
                output_node_ids=("6",),
                execution_options=ExecutionOptions(production_enabled=True),
                request_metadata=dict(request_metadata or {}),
                validation={},
                deployment_identity={},
            )

        with self._service_patcher(), mock.patch(
            "canonical_execution.build_execution_plan", fake_canonical_build_empty
        ):
            plan, err = swr.build_workflow_execution_plan(
                bundle, values,
                modal_options={"production": {"enabled": True}},
            )
        self.assertIsNone(err, f"production plan build failed: {err}")
        self.assertEqual(dict(plan.validation), {})
        self.assertEqual(dict(plan.deployment_identity), {})
        # The serialized plan also carries empty identity (no synthesis).
        self.assertEqual(plan.to_dict()["validation"], {})
        self.assertEqual(plan.to_dict()["deployment_identity"], {})

    def test_production_fail_closed_identity_not_fabricated(self):
        """Real canonical build with NO deployment source fails closed: the
        rebuilt plan preserves the empty identity fields exactly as the
        canonical plan carried them (never recomputed), while the collected
        validation proof still flows through verbatim."""
        bundle = self._bundle()
        values = self._merged_values(bundle)
        saved_env = os.environ.pop("COMFYMODAL_V2_DEPLOYMENT_COMBINED_HASH", None)
        patcher, captured = self._recording_build()
        try:
            with self._service_patcher(), mock.patch.object(
                canonical_execution, "_read_baked_custom_node_manifest",
                return_value={}
            ), mock.patch.object(
                canonical_execution, "_compute_host_deployment_combined_hash",
                return_value=""
            ), mock.patch.object(
                canonical_execution, "_read_persisted_deployment_combined_hash",
                return_value=""
            ), _stub_nodes(mappings={}), patcher:
                plan, err = swr.build_workflow_execution_plan(
                    bundle, values,
                    modal_options={"production": {"enabled": True}},
                )
        finally:
            if saved_env is None:
                os.environ.pop("COMFYMODAL_V2_DEPLOYMENT_COMBINED_HASH", None)
            else:
                os.environ["COMFYMODAL_V2_DEPLOYMENT_COMBINED_HASH"] = saved_env
        self.assertIsNone(err, f"production plan build failed: {err}")
        canonical = captured["canonical"]

        # Preserved verbatim, and the identity is genuinely absent (fail-closed).
        self.assertEqual(dict(plan.deployment_identity), dict(canonical.deployment_identity))
        dep = dict(plan.deployment_identity)
        self.assertIs(dep["complete"], False)
        self.assertEqual(dep["deployment_combined_hash"], "")
        self.assertEqual(dep["custom_nodes_generation"], "")
        self.assertEqual(dep["registry_fingerprint"], "")
        self.assertEqual(_norm(plan.validation), _norm(canonical.validation))
        val = _norm(plan.validation)
        self.assertEqual(val["validated"], True)
        self.assertEqual(val["source"], "host_validate_prompt")
        self.assertEqual(val["validated_workflow_hash"], plan.workflow_hash)

    # ── 5. Phase C repair + hash unchanged ───────────────────────────────

    def test_production_phase_c_repair_and_hash_unchanged(self):
        """The reconstruction preserves the canonical plan's repaired workflow
        and hash verbatim: Phase C CLIP links land on the plan workflow and the
        plan hash still binds to the repaired workflow (unchanged)."""
        bundle = self._clip_repair_bundle()
        values = self._merged_values(bundle, {"steps": 30})

        os.environ["COMFYMODAL_V2_DEPLOYMENT_COMBINED_HASH"] = "dep_phase_c"
        patcher, captured = self._recording_build()
        with self._service_patcher(), mock.patch.object(
            canonical_execution, "_read_baked_custom_node_manifest",
            return_value={"production_custom_node_generation": "g_pc",
                          "overall_dependency_hash": "odh_pc"},
        ), patcher, _stub_nodes():
            plan, err = swr.build_workflow_execution_plan(
                bundle, values,
                modal_options={"production": {"enabled": True}},
            )
        self.assertIsNone(err, f"production plan build failed: {err}")
        self.assertIsInstance(plan, ExecutionPlan)
        canonical = captured["canonical"]

        # The reconstruction changed NOTHING about the canonical workflow/hash.
        self.assertEqual(dict(plan.workflow), dict(canonical.workflow))
        self.assertEqual(plan.workflow_hash, canonical.workflow_hash)
        self.assertEqual(plan.source_workflow_hash, canonical.source_workflow_hash)

        # Phase C repair still lands on the plan workflow and the hash binds to
        # the REPAIRED workflow exactly as before the reconstruction.
        wf = swr._plain_copy(plan.workflow)
        self.assertEqual(wf["67"]["inputs"]["clip"], ["62", 0])
        self.assertEqual(wf["169"]["inputs"]["clip"], ["62", 0])
        self.assertEqual(wf["62"]["class_type"], "CLIPLoader")
        self.assertEqual(wf["3"]["inputs"]["steps"], 30)
        self.assertEqual(plan.workflow_hash, prompt_sha256(wf))

        # deployment_identity preserved through the reconstruction here too.
        self.assertEqual(dict(plan.deployment_identity), dict(canonical.deployment_identity))

    # ── shared builder for the round-trip test ───────────────────────────

    def _build_rebuilt_production_plan_with_identity(self) -> ExecutionPlan:
        """Rebuild a production plan whose canonical plan carries a non-empty
        validation proof + deployment identity (fake canonical seam)."""
        bundle = self._bundle()
        values = self._merged_values(bundle)

        def fake_canonical_build(workflow, *, prompt_id="", client_id="",
                                 input_images=None, modal_options=None,
                                 production_options=None, production_report=None,
                                 gpu="", workspace=None, request_metadata=None,
                                 comfyui_root="", trace=None, validate=True,
                                 collect_validation_proof=False):
            return ExecutionPlan(
                workflow=workflow,
                workflow_hash=prompt_sha256(workflow),
                source_workflow_hash=prompt_sha256(workflow),
                production_report={"enabled": True, "output_node_ids": ["6"]},
                model_stack={"model": "krea_model.safetensors"},
                prompt_bundle={"canonical_bundle_marker": True},
                output_node_ids=("6",),
                input_images={},
                execution_options=ExecutionOptions(
                    production_enabled=True,
                    production_output_node_ids=("6",),
                ),
                request_metadata={
                    **dict(request_metadata or {}),
                    "prompt_id": prompt_id or "canonical_pid",
                    "client_id": "canonical_cid",
                    "selected_gpu": gpu or "gpu_test",
                    "workspace_id": "ws_test",
                    "request_origin_info": {"origin": "studio_test"},
                },
                validation=dict(_VALIDATION_PAYLOAD),
                deployment_identity=_DEPLOYMENT_IDENTITY,
            )

        with self._service_patcher(), mock.patch(
            "canonical_execution.build_execution_plan", fake_canonical_build
        ):
            plan, err = swr.build_workflow_execution_plan(
                bundle, values,
                modal_options={"production": {"enabled": True}},
            )
        self.assertIsNone(err, f"production plan build failed: {err}")
        return plan


if __name__ == "__main__":
    unittest.main()
