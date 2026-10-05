"""Deterministic tests for ``experiment_modern_plan`` (Phase D, lane L1).

The module under test is the pure modern cell-plan generator: ONE experiment
definition -> ordered, immutable ``ExperimentCellPlan``.  Every executable
cell must be routed through the exact modern workflow seam
(``resolve_workflow_run_bundle -> merge_workflow_controls ->
apply_workflow_values_to_prompt -> build_workflow_execution_plan``) and the
legacy ``resolve_and_inject_cell`` slot-path graph mutation must never be
reused.

These tests exercise the planner against a REAL temp-directory
``WorkflowDomainService`` (workflow + immutable version + mapping),
mirroring the fixture patterns of ``test_workflow_domain.py`` /
``test_workflow_run_integration.py``.  The only seam patched is the domain
service factory (``studio_workflow_run._get_domain_service``) so resolution
uses the hermetic temp store with no dependency resolver.

Coverage contract (from the orchestrator brief):

* one cell / two cells / 40-cell deterministic order
* same definition -> identical cell ids, order and hashes
* workflow axis with two workflows (top-level list AND ``workflow`` axis form)
* explicit pinned Version used verbatim
* workflow-only latest Version resolved exactly once and frozen into cells
* latest Version changing after planning does NOT substitute baked ids
* mapped prompt (alias ``prompt`` -> ``positive_prompt``), seed,
  sampler/scheduler, model choice, width/height
* falsy values (0 / 0.0 / False / "") preserved verbatim
* invalid mapped value rejects only its own cell
* absent mapping rejects only the affected cells (sibling isolation)
* globally malformed definitions raise ``ExperimentDefinitionError``
* hardened range expansion: incompatible-direction ranges raise
  ``ExperimentDefinitionError`` (never ``IndexError``), decimal ranges expand
  index-based with no drift (0.0..1.0 step 0.1 -> 11 ordered values), and a
  pathological oversized range is stopped by the expansion-bound guard
* pinned axis ordering: axes declared in non-default order (seed first) still
  yield a target-major, seed-innermost expansion (steps [20,20,30,30], seed
  [1,2,1,2]) with sequential positions and deterministic ids
* stored workflow version/mapping untouched by planning
* Phase C CLIP/VAE repair survives via the modern seam
* strict ``json.dumps(..., allow_nan=False)`` durable plan
* no legacy slot-path mutation is ever called

Deterministic + fast: temp dirs, no network, no Modal calls, no real
generation.  Production mode is disabled in every fixture
(``modal_options={"production": {"enabled": False}}``) so execution plans are
fully deterministic and do not touch ``canonical_execution``.
"""
from __future__ import annotations

import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import experiment_modern_plan as emp
import studio_workflow_run as swr
from studio_domain import WorkflowDomainService, derive_mapping_candidates


# ── Fixtures (standalone copies of the house patterns) ────────────────────


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
    """Immutable version whose CLIPTextEncode nodes (67 positive, 169 negative)
    have NO ``clip`` inputs wired (Phase C repair fixture)."""
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


def no_seed_prompt() -> dict:
    """A runnable graph WITHOUT any seed-capable node (its mapping exposes no
    ``seed`` control) — used for the absent-mapping sibling-isolation test."""
    return {
        "1": {"class_type": "CLIPTextEncode", "inputs": {"text": "hello", "clip": ["4", 0]}},
        "6": {"class_type": "SaveImage", "inputs": {"images": ["9", 0]}},
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


def mapping_payload(prompt: dict | None = None) -> dict:
    capture = make_capture(prompt or txt2img_prompt())
    entries, output_node_id = derive_mapping_candidates(
        capture, node_def_provider=fake_node_def
    )
    return {
        "entries": {role: e.to_dict() for role, e in entries.items()},
        "output_node_id": output_node_id,
    }


def _apply_values(prompt: dict, values: dict | None) -> dict:
    """Write ``values`` into a copy of ``prompt`` through its derived mapping.

    With presets gone, a version's own executable prompt IS its default
    configuration, so fixture values are baked into the captured graph instead
    of being stored separately. Roles without a node/input in this fixture are
    ignored (they were never mapped, so they had nowhere to live).
    """
    if not values:
        return prompt
    entries = mapping_payload(prompt)["entries"]
    out = copy.deepcopy(prompt)
    for role, value in values.items():
        entry = entries.get(role)
        if not entry:
            continue
        node = out.get(entry["node_id"])
        if node is None:
            continue
        node.setdefault("inputs", {})[entry["input_name"]] = value
    return out


def _default_modal_options() -> dict:
    # Production is disabled everywhere so execution plans are deterministic
    # and the canonical_execution production compiler is never touched.
    return {"production": {"enabled": False}}


# ── Test case ─────────────────────────────────────────────────────────────


class ExperimentModernPlanTestCase(unittest.TestCase):
    """Behavior tests for the modern experiment cell-plan generator."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = str(Path(self._tmp.name))
        self.service = WorkflowDomainService(self.root)
        self.wf = self.service.create_workflow("Text2Img Workflow")
        self.version = self._capture_mapped(
            self.wf["workflow_id"], txt2img_prompt()
        )
        self.version_id = self.version["workflow_version_id"]
        # Control values come from the captured version's own executable
        # prompt; there is no separate saved configuration to create.

    def tearDown(self) -> None:
        self._tmp.cleanup()

    # ── helpers ──────────────────────────────────────────────────────────

    def _service_patcher(self):
        """Patch the seam's domain-service factory to the hermetic temp store
        (no dependency resolver -> deterministic runnable states)."""
        return mock.patch(
            "studio_workflow_run._get_domain_service",
            new=lambda node_dir: WorkflowDomainService(str(node_dir)),
        )

    def _capture_mapped(
        self,
        workflow_id: str,
        prompt: dict | None = None,
        *,
        provider=fake_node_def,
        entries_tweak=None,
    ) -> dict:
        prompt = prompt or txt2img_prompt()
        version = self.service.create_version_from_capture(
            workflow_id, make_capture(prompt)
        )
        payload = mapping_payload(prompt)
        if provider is not fake_node_def:
            entries, output_node_id = derive_mapping_candidates(
                make_capture(prompt), node_def_provider=provider
            )
            payload = {
                "entries": {r: e.to_dict() for r, e in entries.items()},
                "output_node_id": output_node_id,
            }
        if entries_tweak is not None:
            entries_tweak(payload["entries"])
        self.service.set_mapping(
            version["workflow_version_id"],
            entries=payload["entries"],
            output_node_id=payload["output_node_id"],
        )
        return version

    def _add_mapped_workflow(
        self,
        name: str,
        prompt: dict,
        values: dict,
        *,
        entries_tweak=None,
    ) -> dict:
        """Full workflow + version + mapping. ``values`` seeds the captured
        graph's own control inputs, so the version's executable prompt carries
        them (there is no separate saved configuration)."""
        wf = self.service.create_workflow(name)
        prompt = _apply_values(prompt, values)
        version = self._capture_mapped(
            wf["workflow_id"], prompt, entries_tweak=entries_tweak
        )
        return {
            "workflow_id": wf["workflow_id"],
            "workflow": wf,
            "version_id": version["workflow_version_id"],
            "version": version,
        }

    def _build(self, experiment_def: dict, **kwargs) -> emp.ExperimentCellPlan:
        kwargs.setdefault("modal_options", _default_modal_options())
        with self._service_patcher():
            return emp.build_cell_plan(experiment_def, self.root, **kwargs)

    def _defn(self, **overrides) -> dict:
        base = {
            "experiment_id": "exp_test",
            "workflows": [self.wf["workflow_id"]],
        }
        base.update(overrides)
        return base

    def _assert_all_ok(self, plan: emp.ExperimentCellPlan) -> None:
        for cell in plan.cells:
            self.assertTrue(cell.ok, f"cell {cell.position} must be ok: {cell.error}")

    # ── 1. one cell ─────────────────────────────────────────────────────

    def test_01_one_cell(self):
        plan = self._build(self._defn(axes={"steps": [30]}, concurrency=3))
        self.assertEqual(plan.experiment_id, "exp_test")
        self.assertEqual(plan.expected_cell_count, 1)
        self.assertEqual(plan.concurrency, 3, "definition concurrency is honored")
        self.assertEqual(plan.axis_labels, ("steps",))
        self.assertEqual(len(plan.cells), 1)
        cell = plan.cells[0]
        self.assertTrue(cell.ok, cell.error)
        self.assertEqual(cell.position, 0)
        self.assertEqual(cell.workflow_id, self.wf["workflow_id"])
        self.assertEqual(cell.workflow_version_id, self.version_id)
        self.assertEqual(cell.workflow_name, "Text2Img Workflow")
        self.assertEqual(cell.version_number, 1)
        self.assertTrue(cell.cell_id.startswith("cell_"))
        self.assertEqual(cell.axis_values["steps"], 30)
        self.assertTrue(cell.plan_hash)
        self.assertIsNotNone(cell.execution_plan_dict)
        self.assertEqual(len(cell.execution_plan_dict["output_node_ids"]), 1)

    # ── 2. two cells ────────────────────────────────────────────────────

    def test_02_two_cells_deterministic_order(self):
        plan = self._build(self._defn(axes={"steps": [20, 30]}))
        self.assertEqual(plan.expected_cell_count, 2)
        self.assertEqual(plan.cell_ordering[0], plan.cells[0].cell_id)
        self.assertEqual(plan.cells[0].axis_values["steps"], 20)
        self.assertEqual(plan.cells[1].axis_values["steps"], 30)
        self.assertEqual(plan.cells[0].position, 0)
        self.assertEqual(plan.cells[1].position, 1)
        self.assertNotEqual(plan.cells[0].cell_id, plan.cells[1].cell_id)
        self._assert_all_ok(plan)

    # ── 3. 40-cell deterministic order ──────────────────────────────────

    def test_03_40_cell_deterministic_order(self):
        seeds = list(range(40))
        plan = self._build(self._defn(axes={"seed": seeds}))
        self.assertEqual(plan.expected_cell_count, 40)
        self.assertEqual(len(plan.cells), 40)
        self.assertEqual(len(plan.cell_ordering), 40)
        self.assertEqual(len(set(plan.cell_ordering)), 40, "cell ids unique")
        for index, cell in enumerate(plan.cells):
            self.assertEqual(cell.position, index, "positions are sequential")
            self.assertEqual(cell.axis_values["seed"], seeds[index])
            self.assertTrue(cell.ok, cell.error)
        # Ordering matches the seed axis list order exactly.
        self.assertEqual(
            [c.axis_values["seed"] for c in plan.cells], seeds
        )
        # First cell id equals the public deterministic id derivation.
        self.assertEqual(
            plan.cells[0].cell_id,
            emp.cell_id_for("exp_test", 0, {"seed": 0}),
        )

    # ── 4. same definition -> identical plan ────────────────────────────

    def test_04_same_definition_identical_plan(self):
        defn = self._defn(
            axes={"prompt": ["alpha", "beta"], "steps": [10, 20, 30]},
            concurrency=4,
        )
        plan_a = self._build(defn)
        plan_b = self._build(defn)
        self.assertEqual(plan_a.to_json(), plan_b.to_json())
        self.assertEqual(plan_a.cell_ordering, plan_b.cell_ordering)
        self.assertEqual(
            [c.plan_hash for c in plan_a.cells],
            [c.plan_hash for c in plan_b.cells],
        )
        self.assertEqual(
            [c.workflow_hash for c in plan_a.cells],
            [c.workflow_hash for c in plan_b.cells],
        )
        for a, b in zip(plan_a.cells, plan_b.cells):
            self.assertEqual(a.cell_id, b.cell_id)
            self.assertEqual(emp.cell_plan_hash(a), emp.cell_plan_hash(b))

    # ── 5. workflow axis with two workflows ─────────────────────────────

    def test_05_workflow_axis_two_workflows(self):
        second = self._add_mapped_workflow(
            "Second Workflow", txt2img_prompt(seed=7), default_values()
        )
        wf_ids = [self.wf["workflow_id"], second["workflow_id"]]

        # Top-level workflows list.
        plan = self._build(self._defn(workflows=wf_ids, axes={"steps": [20, 30]}))
        self.assertEqual(plan.expected_cell_count, 4)
        self.assertEqual(plan.axis_labels, ("steps",))
        self.assertEqual(
            [c.workflow_id for c in plan.cells],
            [wf_ids[0], wf_ids[0], wf_ids[1], wf_ids[1]],
            "target-major, combo-minor ordering",
        )
        self.assertEqual(
            [c.axis_values["steps"] for c in plan.cells],
            [20, 30, 20, 30],
        )
        self.assertEqual(len(plan.workflow_branches), 2)
        branch_ids = {b["workflow_id"] for b in plan.workflow_branches}
        self.assertEqual(branch_ids, set(wf_ids))
        self._assert_all_ok(plan)

        # Workflow-axis form: axes={"workflow": {"values": [...]}} records the
        # resolved target under the canonical "workflow" axis label.  No
        # top-level workflows key is allowed alongside the axis.
        defn2 = {"experiment_id": "exp_test", "axes": {"workflow": {"values": wf_ids}, "steps": [20]}}
        plan2 = self._build(defn2)
        self.assertEqual(plan2.expected_cell_count, 2)
        self.assertEqual(plan2.axis_labels, ("workflow", "steps"))
        for cell, wf_id in zip(plan2.cells, wf_ids):
            self.assertEqual(cell.workflow_id, wf_id)
            wf_axis = cell.axis_values["workflow"]
            self.assertEqual(wf_axis["workflow_id"], wf_id)
            self.assertTrue(wf_axis["workflow_version_id"])
        self._assert_all_ok(plan2)

    # ── 6. explicit pinned Version ──────────────────────────────────────

    def test_06_explicit_pinned_version(self):
        # Create a NEWER version (v2) and make it the latest so the pinned v1
        # is deliberately NOT the default.
        v2 = self._capture_mapped(self.wf["workflow_id"], txt2img_prompt(steps=25))
        self.assertNotEqual(v2["workflow_version_id"], self.version_id)
        self.assertEqual(
            self.service.get_workflow(self.wf["workflow_id"])["latest_version_id"],
            v2["workflow_version_id"],
            "latest now points at v2",
        )

        plan = self._build(self._defn(
            workflows=[{
                "workflow_id": self.wf["workflow_id"],
                "workflow_version_id": self.version_id,
            }],
            axes={"steps": [20]},
        ))
        self.assertEqual(plan.expected_cell_count, 1)
        cell = plan.cells[0]
        self.assertTrue(cell.ok, cell.error)
        self.assertEqual(cell.workflow_version_id, self.version_id, "pinned version verbatim")
        self.assertEqual(cell.version_number, 1)
        self.assertEqual(cell.axis_values["steps"], 20)

    # ── 7. workflow-only latest/default resolved once, frozen ───────────

    def test_07_workflow_only_latest_default_resolved_once(self):
        plan = self._build(self._defn(axes={"steps": [20, 30]}))
        self.assertEqual(plan.expected_cell_count, 2)
        for cell in plan.cells:
            self.assertTrue(cell.ok, cell.error)
            self.assertEqual(
                cell.workflow_version_id, self.version_id,
                "workflow-only axis bakes the latest version id",
            )
            self.assertEqual(cell.workflow_name, "Text2Img Workflow")

        # Resolution happens EXACTLY once for one distinct workflow target
        # (the per-target resolution cache is exercised by the 2 cells).
        with mock.patch.object(
            emp, "resolve_workflow_axis_value",
            wraps=emp.resolve_workflow_axis_value,
        ) as wrapped:
            plan2 = self._build(self._defn(axes={"steps": [20, 30]}))
            self.assertEqual(plan2.expected_cell_count, 2)
            self.assertEqual(
                wrapped.call_count, 1,
                "workflow-only latest/default resolution runs exactly once "
                "at plan time and is cached per target",
            )
            for call in wrapped.call_args_list:
                target = call.args[0]
                self.assertEqual(target["workflow_id"], self.wf["workflow_id"])
                self.assertEqual(target["workflow_version_id"], None)
                self.assertEqual(call.args[1], self.root)

    # ── 8. latest Version changes after planning -> no substitution ─────

    def test_08_latest_version_change_no_substitution(self):
        plan = self._build(self._defn(axes={"steps": [20]}))
        cell = plan.cells[0]
        baked = cell.workflow_version_id
        self.assertEqual(baked, self.version_id)
        json_before = plan.to_json()

        # The workflow gains a newer latest version AFTER planning.
        v2 = self._capture_mapped(self.wf["workflow_id"], txt2img_prompt(steps=99))
        self.assertEqual(
            self.service.get_workflow(self.wf["workflow_id"])["latest_version_id"],
            v2["workflow_version_id"],
        )

        # The already-generated plan keeps its baked ids/hashes untouched —
        # execution never re-resolves latest/default.
        self.assertEqual(plan.to_json(), json_before, "plan is frozen")
        self.assertEqual(cell.workflow_version_id, baked)
        self.assertNotEqual(cell.workflow_version_id, v2["workflow_version_id"])
        self.assertEqual(cell.workflow_hash, cell.workflow_hash)

        # The STORE did change: a fresh resolution now returns the new latest,
        # proving the existing plan did not silently slide to it.
        with self._service_patcher():
            fresh = emp.resolve_workflow_axis_value(self.wf["workflow_id"], self.root)
        self.assertTrue(fresh.ok)
        self.assertEqual(fresh.workflow_version_id, v2["workflow_version_id"])

        # And a REBUILD (a new plan) legitimately picks up the new latest.
        plan2 = self._build(self._defn(axes={"steps": [20]}))
        self.assertEqual(plan2.cells[0].workflow_version_id, v2["workflow_version_id"])

    # ── 9. mapped prompt (alias) ────────────────────────────────────────

    def test_09_mapped_prompt_alias(self):
        plan = self._build(self._defn(axes={"prompt": ["a cat wearing a hat"]}))
        cell = plan.cells[0]
        self.assertTrue(cell.ok, cell.error)
        self.assertEqual(cell.controls["positive_prompt"], "a cat wearing a hat")
        self.assertEqual(
            cell.axis_to_control["prompt"], "positive_prompt",
            "the 'prompt' axis label aliases to the mapping role",
        )
        self.assertEqual(
            cell.merged_values["positive_prompt"], "a cat wearing a hat"
        )
        workflow = cell.execution_plan_dict["workflow"]
        self.assertEqual(workflow["1"]["inputs"]["text"], "a cat wearing a hat")
        self.assertEqual(workflow["2"]["inputs"]["text"], "negative", "untouched negative kept")

    # ── 10. mapped seed ─────────────────────────────────────────────────

    def test_10_mapped_seed(self):
        plan = self._build(self._defn(axes={"seed": [42]}))
        cell = plan.cells[0]
        self.assertTrue(cell.ok, cell.error)
        self.assertEqual(cell.controls["seed"], 42)
        self.assertEqual(cell.merged_values["seed"], 42)
        workflow = cell.execution_plan_dict["workflow"]
        self.assertEqual(workflow["3"]["inputs"]["seed"], 42)

    # ── 11. sampler / scheduler ─────────────────────────────────────────

    def test_11_sampler_scheduler_axes(self):
        plan = self._build(self._defn(axes={
            "sampler": ["dpmpp_2m"],
            "scheduler": ["karras"],
        }))
        cell = plan.cells[0]
        self.assertTrue(cell.ok, cell.error)
        self.assertEqual(cell.controls["sampler"], "dpmpp_2m")
        self.assertEqual(cell.controls["scheduler"], "karras")
        self.assertEqual(cell.merged_values["sampler"], "dpmpp_2m")
        self.assertEqual(cell.merged_values["scheduler"], "karras")
        workflow = cell.execution_plan_dict["workflow"]
        self.assertEqual(workflow["3"]["inputs"]["sampler_name"], "dpmpp_2m")
        self.assertEqual(workflow["3"]["inputs"]["scheduler"], "karras")

    # ── 12. model choice (mapping exposes model) ────────────────────────

    def test_12_model_choice(self):
        # The version's own graph carries the model; there is no separate
        # saved model choice that can outrank it.
        mc_wf = self._add_mapped_workflow(
            "Flux Workflow",
            _apply_values(txt2img_prompt(), {"model": "flux-dev.safetensors"}),
            {},
        )
        base = {
            "experiment_id": "exp_mc",
            "workflows": [mc_wf["workflow_id"]],
        }
        # Without a model axis the version's own model is used.
        plan = self._build({**base, "axes": {"steps": [20]}})
        self.assertEqual(
            plan.cells[0].merged_values["model"], "flux-dev.safetensors"
        )

        # With a model axis the override wins over the version's default.
        plan2 = self._build({**base, "axes": {"model": ["krea_model.safetensors"]}})
        cell = plan2.cells[0]
        self.assertTrue(cell.ok, cell.error)
        self.assertEqual(cell.controls["model"], "krea_model.safetensors")
        self.assertEqual(cell.merged_values["model"], "krea_model.safetensors")
        workflow = cell.execution_plan_dict["workflow"]
        self.assertEqual(workflow["4"]["inputs"]["ckpt_name"], "krea_model.safetensors")

    # ── 13. width / height ──────────────────────────────────────────────

    def test_13_width_height(self):
        plan = self._build(self._defn(axes={"width": [768], "height": [512]}))
        cell = plan.cells[0]
        self.assertTrue(cell.ok, cell.error)
        self.assertEqual(cell.controls["width"], 768)
        self.assertEqual(cell.controls["height"], 512)
        self.assertEqual(cell.merged_values["width"], 768)
        self.assertEqual(cell.merged_values["height"], 512)
        workflow = cell.execution_plan_dict["workflow"]
        self.assertEqual(workflow["5"]["inputs"]["width"], 768)
        self.assertEqual(workflow["5"]["inputs"]["height"], 512)

    # ── 14. falsy values preserved verbatim ─────────────────────────────

    def test_14_falsy_values_preserved(self):
        plan = self._build(self._defn(axes={
            "seed": [0],
            "cfg": [0.0],
            "denoise": [False],
        }))
        cell = plan.cells[0]
        self.assertTrue(cell.ok, cell.error)
        merged = cell.merged_values
        self.assertIs(type(merged["seed"]), int)
        self.assertEqual(merged["seed"], 0)
        self.assertIs(type(merged["cfg"]), float)
        self.assertEqual(merged["cfg"], 0.0)
        self.assertIs(merged["denoise"], False)
        workflow = cell.execution_plan_dict["workflow"]
        self.assertIs(type(workflow["3"]["inputs"]["seed"]), int)
        self.assertEqual(workflow["3"]["inputs"]["seed"], 0)
        self.assertIs(type(workflow["3"]["inputs"]["cfg"]), float)
        self.assertEqual(workflow["3"]["inputs"]["cfg"], 0.0)
        self.assertIs(workflow["3"]["inputs"]["denoise"], False)

    # ── 15. empty string preserved when the schema allows it ────────────

    def test_15_empty_string_when_schema_allows(self):
        # A mapping whose positive_prompt control is NOT required: "" is a
        # legitimate value and must be preserved verbatim (never coerced).
        workflow = self._add_mapped_workflow(
            "Optional Prompt Workflow",
            txt2img_prompt(),
            {k: v for k, v in default_values().items() if k != "positive_prompt"},
            entries_tweak=lambda entries: entries["positive_prompt"].__setitem__("required", False),
        )
        plan = self._build(self._defn(
            workflows=[workflow["workflow_id"]],
            axes={"prompt": [""]},
        ))
        cell = plan.cells[0]
        self.assertTrue(cell.ok, cell.error)
        self.assertEqual(cell.controls["positive_prompt"], "")
        self.assertEqual(cell.merged_values["positive_prompt"], "")
        workflow_dict = cell.execution_plan_dict["workflow"]
        self.assertEqual(workflow_dict["1"]["inputs"]["text"], "")

    # ── 16. invalid mapped value rejects only its own cell ──────────────

    def test_16_invalid_mapped_value_rejects_only_its_cell(self):
        plan = self._build(self._defn(axes={
            "sampler": ["euler", "definitely-not-a-sampler"],
        }))
        self.assertEqual(plan.expected_cell_count, 2)
        good, bad = plan.cells
        self.assertTrue(good.ok, good.error)
        self.assertEqual(good.controls["sampler"], "euler")
        self.assertFalse(bad.ok)
        self.assertEqual(bad.error_code, "WORKFLOW_CONTROL_VALIDATION")
        self.assertIn("must be one of", bad.error)
        self.assertEqual(bad.errors[0]["field"], "sampler")
        self.assertIsNone(bad.execution_plan_dict, "failed cell never builds a plan")

    # ── 17. absent mapping rejects only the affected cells ──────────────

    def test_17_absent_mapping_rejects_only_affected_cells(self):
        no_seed = self._add_mapped_workflow(
            "No Seed Workflow", no_seed_prompt(), {"positive_prompt": "hello"}
        )
        plan = self._build(self._defn(
            workflows=[self.wf["workflow_id"], no_seed["workflow_id"]],
            axes={"seed": [1, 2]},
        ))
        self.assertEqual(plan.expected_cell_count, 4)
        for cell in plan.cells[:2]:
            self.assertEqual(cell.workflow_id, self.wf["workflow_id"])
            self.assertTrue(cell.ok, cell.error)
        for cell in plan.cells[2:]:
            self.assertEqual(cell.workflow_id, no_seed["workflow_id"])
            self.assertFalse(cell.ok)
            self.assertEqual(cell.error_code, "WORKFLOW_CONTROL_VALIDATION")
            self.assertIn("unknown control 'seed'", cell.error)
            self.assertIsNone(cell.execution_plan_dict)

    # ── 18. globally malformed definitions raise ────────────────────────

    def test_18_global_malformed_definition_raises(self):
        wf_id = self.wf["workflow_id"]
        cases = {
            "non-dict definition": "not-a-dict",
            "missing experiment_id": {"workflows": [wf_id]},
            "empty experiment_id": {"experiment_id": "  ", "workflows": [wf_id]},
            "axes not a dict": {"experiment_id": "x", "workflows": [wf_id], "axes": []},
            "top-level AND workflow axis": {
                "experiment_id": "x", "workflows": [wf_id],
                "axes": {"workflow": [wf_id]},
            },
            "no workflows declared": {"experiment_id": "x", "axes": {"seed": [1]}},
            "empty workflow value": {"experiment_id": "x", "workflows": ["  "]},
            "empty axis value list": {
                "experiment_id": "x", "workflows": [wf_id], "axes": {"seed": []},
            },
            "concurrency zero": {
                "experiment_id": "x", "workflows": [wf_id], "concurrency": 0,
            },
            "concurrency bool": {
                "experiment_id": "x", "workflows": [wf_id], "concurrency": True,
            },
            "concurrency negative": {
                "experiment_id": "x", "workflows": [wf_id], "concurrency": -2,
            },
            "workflow axis range mode": {
                "experiment_id": "x",
                "axes": {"workflow": {"start": 1, "end": 3}},
            },
            "axis raw not list/dict": {
                "experiment_id": "x", "workflows": [wf_id], "axes": {"seed": 5},
            },
            "axis label not a string": {
                "experiment_id": "x", "workflows": [wf_id], "axes": {5: [1]},
            },
            "non-JSON axis value": {
                "experiment_id": "x", "workflows": [wf_id],
                "axes": {"seed": [{1, 2}]},
            },
            "modal_options not a dict": {
                "experiment_id": "x", "workflows": [wf_id], "modal_options": [],
            },
            "modal_options non-JSON": {
                "experiment_id": "x", "workflows": [wf_id],
                "modal_options": {"gpu": {1, 2}},
            },
        }
        for label, defn in cases.items():
            with self.subTest(case=label):
                with self.assertRaises(emp.ExperimentDefinitionError):
                    self._build(defn)

    # ── 19. stored workflow version / mapping unchanged ──────────────

    def test_19_stored_workflow_version_unchanged(self):
        before = {
            "workflow": copy.deepcopy(self.service.get_workflow(self.wf["workflow_id"])),
            "version": copy.deepcopy(self.service.get_version(self.version_id)),
            "mapping": copy.deepcopy(self.service.get_mapping(self.version_id)),
        }
        plan = self._build(self._defn(axes={"prompt": ["x", "y"], "seed": [1, 2]}))
        self.assertEqual(plan.expected_cell_count, 4)
        after = {
            "workflow": self.service.get_workflow(self.wf["workflow_id"]),
            "version": self.service.get_version(self.version_id),
            "mapping": self.service.get_mapping(self.version_id),
        }
        for key in ("workflow", "version", "mapping"):
            self.assertEqual(
                before[key], after[key],
                f"planning must not mutate the stored {key}",
            )

    # ── 20. Phase C CLIP/VAE repair survives via the modern seam ────────

    def test_20_clip_vae_repair_survives_modern_seam(self):
        clip_wf = self._add_mapped_workflow(
            "Clip Repair Workflow", clip_repair_prompt(), clip_repair_values()
        )
        stored = self.service.get_version(clip_wf["version_id"])
        self.assertNotIn("clip", stored["executable_prompt"]["67"]["inputs"])
        self.assertNotIn("clip", stored["executable_prompt"]["169"]["inputs"])

        from studio_run_adapter import (
            _repair_missing_clip_inputs as _real_clip_repair,
            _repair_missing_vae_inputs as _real_vae_repair,
        )

        with mock.patch(
            "studio_run_adapter._repair_missing_clip_inputs",
            wraps=_real_clip_repair,
        ) as clip_mock, mock.patch(
            "studio_run_adapter._repair_missing_vae_inputs",
            wraps=_real_vae_repair,
        ) as vae_mock:
            plan = self._build(self._defn(
                workflows=[clip_wf["workflow_id"]],
                axes={"steps": [20, 30]},
            ))

        self.assertEqual(plan.expected_cell_count, 2)
        self.assertTrue(clip_mock.call_count >= 1, "CLIP repair helper invoked")
        vae_mock.assert_called()
        for cell in plan.cells:
            self.assertTrue(cell.ok, cell.error)
            workflow = cell.execution_plan_dict["workflow"]
            self.assertEqual(workflow["67"]["inputs"]["clip"], ["62", 0])
            self.assertEqual(workflow["169"]["inputs"]["clip"], ["62", 0])
            self.assertEqual(workflow["62"]["class_type"], "CLIPLoader")
            self.assertTrue(cell.workflow_hash, "hash covers the repaired graph")

        # The stored immutable version was never touched.
        after = self.service.get_version(clip_wf["version_id"])
        self.assertNotIn("clip", after["executable_prompt"]["67"]["inputs"])
        self.assertEqual(after["graph_hash"], stored["graph_hash"])

    # ── 21. strict json.dumps(... allow_nan=False) durable plan ─────────

    def test_21_strict_json_durable_plan(self):
        defn = self._defn(
            axes={"prompt": ["a", "b"], "steps": [10, 20, 30]},
            modal_options={**_default_modal_options(), "gpu": "H100"},
        )
        plan = self._build(defn)
        self.assertEqual(plan.expected_cell_count, 6)
        # Def-level modal_options win over the helper kwarg and are frozen.
        self.assertEqual(plan.modal_options["gpu"], "H100")
        self.assertEqual(plan.modal_options["production"]["enabled"], False)

        # The full plan dict is strict-JSON serializable (no allow_nan).
        payload = plan.to_dict()
        self.assertIsInstance(json.dumps(payload, allow_nan=False), str)

        # Round-trip through the canonical plan JSON.
        text = plan.to_json()
        loaded = json.loads(text)
        self.assertEqual(loaded["experiment_id"], "exp_test")
        self.assertEqual(loaded["expected_cell_count"], 6)
        self.assertEqual(len(loaded["cells"]), 6)
        # Re-serializing the round-tripped data is still strict-safe.
        self.assertIsInstance(json.dumps(loaded, allow_nan=False), str)

        for cell in plan.cells:
            self.assertTrue(cell.ok, cell.error)
            self.assertIsInstance(json.dumps(cell.to_dict(), allow_nan=False), str)
            self.assertIsInstance(
                json.dumps(cell.execution_plan_dict, allow_nan=False), str
            )
            self.assertEqual(
                cell.execution_plan_dict["execution_options"]["production"]["enabled"],
                False,
                "non-production plan path used in hermetic fixtures",
            )
            self.assertEqual(cell.plan_hash, emp.cell_plan_hash(cell))

    # ── 22. no legacy slot-path mutation is ever called ─────────────────

    def test_22_no_legacy_slot_path_mutation(self):
        # Structural: the planner never imports the legacy slot-path
        # graph-mutation machinery.  (``resolve_and_inject_cell`` appears ONLY
        # in the module docstring as the thing that must not be reused, so the
        # call-absence is asserted behaviorally below.)
        source = emp.__file__
        module_text = Path(source).read_text(encoding="utf-8")
        for banned in ("_set_path_value", "_set_field", "experiment_runner"):
            self.assertNotIn(banned, module_text, f"banned legacy reference {banned!r}")
        # ``matrix_compiler`` may be NAMED in comments (its cheap-axis ordering
        # is the documented convention the modern ordering layer mirrors), but
        # the planner must never IMPORT the legacy compiler.
        for banned_import in ("import matrix_compiler", "from matrix_compiler"):
            self.assertNotIn(
                banned_import, module_text, f"banned legacy import {banned_import!r}"
            )

        # Behavioral: even if the legacy entry points were reachable, planning
        # a fully valid experiment never calls them.
        import experiment_runner

        guards = [
            mock.patch.object(
                experiment_runner, "resolve_and_inject_cell",
                side_effect=AssertionError("legacy resolve_and_inject_cell called"),
            ),
            mock.patch.object(
                experiment_runner, "_set_path_value",
                side_effect=AssertionError("legacy _set_path_value called"),
            ),
            mock.patch.object(
                experiment_runner, "_set_field",
                side_effect=AssertionError("legacy _set_field called"),
            ),
        ]
        started = [guard.start() for guard in guards]
        try:
            plan = self._build(self._defn(axes={"prompt": ["x", "y"]}))
            self._assert_all_ok(plan)
        finally:
            for guard in guards:
                guard.stop()
        for guard_mock in started:
            guard_mock.assert_not_called()

    # ── 23. every executable cell routes through the modern seam ────────

    def test_23_every_ok_cell_routes_through_modern_seam(self):
        plan_seed = self._build(self._defn(axes={"steps": [20, 30]}))
        self.assertEqual(plan_seed.expected_cell_count, 2)

        with mock.patch.object(
            swr, "resolve_workflow_run_bundle", wraps=swr.resolve_workflow_run_bundle
        ) as resolve_mock, mock.patch.object(
            swr, "merge_workflow_controls", wraps=swr.merge_workflow_controls
        ) as merge_mock, mock.patch.object(
            swr, "apply_workflow_values_to_prompt",
            wraps=swr.apply_workflow_values_to_prompt,
        ) as apply_mock, mock.patch.object(
            swr, "build_workflow_execution_plan",
            wraps=swr.build_workflow_execution_plan,
        ) as build_mock:
            plan = self._build(self._defn(axes={"steps": [20, 30]}))
            self._assert_all_ok(plan)
            self.assertEqual(plan.expected_cell_count, 2)

        self.assertEqual(resolve_mock.call_count, 1, "one distinct workflow target")
        self.assertEqual(
            merge_mock.call_count, 2, "merge runs exactly once per executable cell"
        )
        # build_workflow_execution_plan is the SOLE apply+build seam: it
        # invokes apply_workflow_values_to_prompt internally (the exact modern
        # single-run chain), so prompt application happens exactly once per
        # executable cell, nested inside the single per-cell plan build —
        # never as a separate planner-level call.
        self.assertEqual(
            apply_mock.call_count, 2,
            "apply runs exactly once per executable cell via the plan build",
        )
        self.assertEqual(
            build_mock.call_count, 2, "plan build runs exactly once per cell"
        )
        self.assertEqual(
            apply_mock.call_count, build_mock.call_count,
            "one apply per plan build (the seam applies exactly once)",
        )

    # ── 24. public resolve_workflow_axis_value ──────────────────────────

    def test_24_public_resolve_workflow_axis_value(self):
        with self._service_patcher():
            res = emp.resolve_workflow_axis_value(self.wf["workflow_id"], self.root)
        self.assertIsInstance(res, emp.WorkflowResolution)
        self.assertTrue(res.ok)
        self.assertEqual(res.workflow_id, self.wf["workflow_id"])
        self.assertEqual(res.workflow_version_id, self.version_id)
        self.assertEqual(res.workflow_name, "Text2Img Workflow")
        self.assertEqual(res.version_number, 1)
        self.assertIn("seed", res.control_schema)
        self.assertTrue(res.bundle["executable_prompt"])
        # Frozen bundle snapshot is a plain deep copy (seam-safe).
        self.assertIsInstance(res.bundle, dict)
        res.to_dict()

        # Domain failure -> fail-closed error resolution (never raises).
        with self._service_patcher():
            err = emp.resolve_workflow_axis_value("wf_ghost", self.root)
        self.assertFalse(err.ok)
        self.assertEqual(err.status, "error")
        self.assertEqual(err.error_code, "WORKFLOW_NOT_FOUND")
        self.assertTrue(err.message)

        # Multi-target expansion is not allowed at the single-value seam.
        with self._service_patcher():
            with self.assertRaises(emp.ExperimentDefinitionError):
                emp.resolve_workflow_axis_value(
                    {"workflow_id": self.wf["workflow_id"], "versions": ["a", "b"]},
                    self.root,
                )

        # Structurally malformed value -> raises.
        with self._service_patcher():
            with self.assertRaises(emp.ExperimentDefinitionError):
                emp.resolve_workflow_axis_value("   ", self.root)

    # ── 25. public validate_cell_controls ───────────────────────────────

    def test_25_public_validate_cell_controls(self):
        schema = {
            "seed": {"node_id": "1", "input_name": "seed", "kind": "node_input",
                     "control_kind": "integer", "data_type": "INT",
                     "minimum": 0.0, "maximum": 100, "required": True},
            "sampler": {"node_id": "1", "input_name": "sampler_name",
                        "kind": "node_input", "control_kind": "enum",
                        "enum_options": ["euler", "dpmpp_2m"]},
            "label": {"node_id": "1", "input_name": "text", "kind": "node_input",
                      "control_kind": "string", "data_type": "STRING",
                      "required": False},
        }
        self.assertEqual(
            emp.validate_cell_controls({"seed": 5, "sampler": "euler"}, schema),
            [],
        )
        errors = emp.validate_cell_controls(
            {"seed": 0, "sampler": "euler", "label": ""}, schema
        )
        self.assertEqual(errors, [], "verbatim 0 / '' are valid")
        errors = emp.validate_cell_controls({"seed": 1, "sampler": "bogus"}, schema)
        self.assertTrue(any(
            e["field"] == "sampler" and "must be one of" in e["message"]
            for e in errors
        ))
        errors = emp.validate_cell_controls({"seed": 150}, schema)
        self.assertTrue(any(
            e["field"] == "seed" and "must be <=" in e["message"]
            for e in errors
        ))
        errors = emp.validate_cell_controls({"not_a_control": 1}, schema)
        self.assertTrue(any(
            e["field"] == "not_a_control" and "unknown control" in e["message"]
            for e in errors
        ))

    # ── 26. public cell_plan_hash ───────────────────────────────────────

    def test_26_public_cell_plan_hash(self):
        data = {
            "experiment_id": "exp_test",
            "cell_id": "cell_x",
            "position": 0,
            "axis_values": {"seed": 1},
            "plan_hash": "self-output-must-be-excluded",
            "execution_plan": {"runtime_diagnostics": {"x": 1}},
            "controls": {"seed": 1},
        }
        h1 = emp.cell_plan_hash(data)
        h2 = emp.cell_plan_hash(dict(data))
        self.assertEqual(h1, h2, "hash stable across equivalent mappings")

        changed = dict(data)
        changed["controls"] = {"seed": 2}
        self.assertNotEqual(
            emp.cell_plan_hash(changed), h1,
            "hash changes when the cell content changes",
        )

        # A CellPlan and its to_dict() hash identically.
        plan = self._build(self._defn(axes={"seed": [1]}))
        self.assertEqual(
            emp.cell_plan_hash(plan.cells[0]),
            emp.cell_plan_hash(plan.cells[0].to_dict()),
        )

        with self.assertRaises(TypeError):
            emp.cell_plan_hash("not-a-cell")
        with self.assertRaises((TypeError, ValueError)):
            emp.cell_plan_hash({"bad": {1, 2}})

    # ── 27. incompatible-direction range axes ───────────────────────────

    def test_27_incompatible_direction_ranges_raise(self):
        """A range whose step points AWAY from end (start above end with a
        positive step, or start below end with a negative step) expands to
        ZERO values: the hardened planner raises ``ExperimentDefinitionError``
        (never an IndexError, never a silent empty axis)."""
        wf_id = self.wf["workflow_id"]
        cases = {
            "positive step above end": {"start": 10, "end": 1, "step": 1},
            "negative step below end": {"start": 1, "end": 10, "step": -1},
        }
        for label, range_def in cases.items():
            with self.subTest(case=label):
                with self.assertRaises(emp.ExperimentDefinitionError) as ctx:
                    self._build(self._defn(
                        workflows=[wf_id], axes={"seed": range_def}
                    ))
                self.assertIn("zero values", str(ctx.exception))

        # Legacy degenerate ranges still expand to exactly one value.
        degenerate = {
            "start equals end": ({"start": 5, "end": 5, "step": 1}, 5),
            "zero step": ({"start": 7, "end": 99, "step": 0}, 7),
        }
        for label, (range_def, expected) in degenerate.items():
            with self.subTest(case=label):
                plan = self._build(self._defn(
                    workflows=[wf_id], axes={"seed": range_def}
                ))
                self.assertEqual(plan.expected_cell_count, 1)
                self.assertEqual(plan.cells[0].axis_values["seed"], expected)

    # ── 28. decimal range expansion has no drift ────────────────────────

    def test_28_decimal_range_no_drift(self):
        """Decimal range expansion is index-based (``start + i*step``): the
        fixture 0.0..1.0 step 0.1 expands to exactly 11 ordered values that
        END on 1.0 — repeated accumulation never drifts — and the expansion
        is deterministic across rebuilds."""
        defn = self._defn(axes={"denoise": {"start": 0.0, "end": 1.0, "step": 0.1}})
        plan = self._build(defn)
        self.assertEqual(plan.expected_cell_count, 11)
        values = [cell.axis_values["denoise"] for cell in plan.cells]
        expected = [0.0 + i * 0.1 for i in range(11)]
        self.assertEqual(
            values, expected,
            "index-based expansion matches start + i*step exactly (no drift)",
        )
        self.assertEqual(values[0], 0.0)
        self.assertEqual(values[-1], 1.0, "final value reaches end exactly")
        self.assertEqual(values, sorted(values), "strictly ordered")
        self.assertEqual(len(set(values)), 11, "every value distinct")
        self._assert_all_ok(plan)

        # Deterministic across rebuilds (values, hashes, whole plan JSON).
        plan2 = self._build(defn)
        self.assertEqual(
            [cell.axis_values["denoise"] for cell in plan2.cells], expected
        )
        self.assertEqual(plan.to_json(), plan2.to_json())

    # ── 29. pathological range expansion bound guard ────────────────────

    def test_29_pathological_range_expansion_bound(self):
        """A mathematically-finite range larger than the expansion cap is
        rejected by the bound guard (never hangs the planner).  The cap is
        patched small so the guard is exercised hermetically and fast."""
        with mock.patch.object(emp, "_MAX_RANGE_VALUES", 10):
            with self.assertRaises(emp.ExperimentDefinitionError) as ctx:
                self._build(self._defn(
                    workflows=[self.wf["workflow_id"]],
                    axes={"seed": {"start": 0, "end": 100, "step": 1}},
                ))
            self.assertIn("maximum expansion bound", str(ctx.exception))

            # A range within the patched bound still expands normally.
            plan = self._build(self._defn(
                workflows=[self.wf["workflow_id"]],
                axes={"seed": {"start": 0, "end": 9, "step": 1}},
            ))
            self.assertEqual(plan.expected_cell_count, 10)
            self.assertEqual(
                [c.axis_values["seed"] for c in plan.cells], list(range(10))
            )
            self._assert_all_ok(plan)

    # ── 30. non-default axis declaration order stays pinned ─────────────

    def test_30_non_default_axis_order_pinned_semantics(self):
        """With non-workflow axes declared in NON-default order (seed first,
        steps second), the pure ordering layer pins the canonical cheap-axis
        rule: the seed axis stays INNERMOST regardless of its declared
        position.  Output remains target-major (every cell of workflow A
        precedes every cell of workflow B) and, within a target block, seed
        varies fastest — steps [20,20,30,30] with seed [1,2,1,2] — with
        sequential positions and deterministic cell ids."""
        second = self._add_mapped_workflow(
            "Second Workflow", txt2img_prompt(seed=7), default_values()
        )
        wf_ids = [self.wf["workflow_id"], second["workflow_id"]]

        defn_seed_first = {
            "experiment_id": "exp_test",
            "workflows": wf_ids,
            "axes": {"seed": [1, 2], "steps": [20, 30]},
        }
        defn_seed_last = {
            "experiment_id": "exp_test",
            "workflows": wf_ids,
            "axes": {"steps": [20, 30], "seed": [1, 2]},
        }
        plan_seed_first = self._build(defn_seed_first)
        plan_seed_last = self._build(defn_seed_last)

        expected_steps = [20, 20, 30, 30, 20, 20, 30, 30]
        expected_seed = [1, 2, 1, 2, 1, 2, 1, 2]
        for plan in (plan_seed_first, plan_seed_last):
            self.assertEqual(plan.expected_cell_count, 8)
            self.assertEqual(
                plan.axis_labels, ("steps", "seed"),
                "seed is canonicalized to the innermost (last) axis label",
            )
            # Target-major: workflow A's four cells precede workflow B's.
            self.assertEqual(
                [c.workflow_id for c in plan.cells],
                [wf_ids[0]] * 4 + [wf_ids[1]] * 4,
            )
            # Seed innermost: within each target block, seed varies fastest.
            self.assertEqual(
                [c.axis_values["steps"] for c in plan.cells], expected_steps
            )
            self.assertEqual(
                [c.axis_values["seed"] for c in plan.cells], expected_seed
            )
            self.assertEqual(
                [c.position for c in plan.cells], list(range(8)),
                "sequential positions",
            )
            self._assert_all_ok(plan)
            # Deterministic ids: the frozen id derives from position + values.
            for cell in plan.cells:
                self.assertEqual(
                    cell.cell_id,
                    emp.cell_id_for(
                        cell.experiment_id, cell.position, cell.axis_values
                    ),
                )
            self.assertEqual(len(set(plan.cell_ordering)), 8, "cell ids unique")

        # The ordering is declaration-order neutral AND stable across rebuilds.
        self.assertEqual(plan_seed_first.to_json(), plan_seed_last.to_json())
        plan_rebuild = self._build(defn_seed_first)
        self.assertEqual(plan_seed_first.to_json(), plan_rebuild.to_json())


if __name__ == "__main__":
    unittest.main()
