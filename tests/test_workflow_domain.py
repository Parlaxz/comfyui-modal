"""Focused tests for the Workflow domain foundation.

Covers: one Workflow with several Versions; one Mapping per Version; many
Presets; default preset; nested folders; tags/favorites; graph enum
metadata; zero/false preservation; preset copy-forward; removed mapped node
→ incomplete state; old Versions stay immutable.
"""

from __future__ import annotations

import copy
import tempfile
import unittest
from pathlib import Path

import pytest

from studio_domain import (
    INPUT_BINDING_KINDS,
    ImmutableVersionError,
    Mapping,
    MappingAlreadyExistsError,
    MappingEntry,
    WorkflowDomainService,
    WorkflowNotRunnableError,
    WorkflowDomainValidationError,
    WorkflowVersion,
    derive_mapping_candidates,
    find_binding_candidates,
    graph_hash_from_capture,
    resolve_binding_target,
)
from studio_domain.services import WorkflowDomainService as _Service  # noqa: F401
from studio_domain.graph import (
    derive_output_node_ids,
    derive_output_node_ids_from_prompt,
    node_has_image_output,
)


# ── fixtures ─────────────────────────────────────────────────────────────


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
    if class_type == "SaveImage":
        return ({"images": ("IMAGE",), "filename_prefix": ("STRING", {"default": "ComfyUI"})}, {})
    return None


class WorkflowDomainTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = str(Path(self._tmp.name))
        self.service = WorkflowDomainService(self.root)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    # ── helpers ──────────────────────────────────────────────────────────

    def create_workflow(self, **kwargs) -> dict:
        return self.service.create_workflow(kwargs.pop("name", "Test Workflow"), **kwargs)

    def create_version(self, workflow_id: str, prompt: dict | None = None) -> dict:
        capture = make_capture(prompt if prompt is not None else txt2img_prompt())
        return self.service.create_version_from_capture(workflow_id, capture)

    def mapping_from_capture(self, capture: dict, workflow_id: str = "") -> dict:
        entries, output_node_id = derive_mapping_candidates(
            capture, node_def_provider=fake_node_def
        )
        return {
            "entries": {role: e.to_dict() for role, e in entries.items()},
            "output_node_id": output_node_id,
        }

    def test_prompt_input_derives_positive_prompt_candidate(self):
        capture = make_capture({
            "1": {
                "class_type": "CustomPromptNode",
                "inputs": {"prompt": "a landscape"},
            },
        })

        def node_def(class_type: str):
            if class_type == "CustomPromptNode":
                return ({"prompt": ("STRING", {"multiline": True})}, {})
            return None

        entries, _ = derive_mapping_candidates(capture, node_def_provider=node_def)

        assert entries["positive_prompt"].node_id == "1"
        assert entries["positive_prompt"].input_name == "prompt"

    def test_negative_prompt_candidate_is_not_required(self):
        capture = make_capture({
            "1": {
                "class_type": "CustomPromptNode",
                "inputs": {"prompt": "a landscape", "negative_prompt": ""},
            },
        })

        def node_def(class_type: str):
            if class_type == "CustomPromptNode":
                return ({"prompt": ("STRING", {"multiline": True}),
                         "negative_prompt": ("STRING", {"multiline": True})}, {})
            return None

        entries, _ = derive_mapping_candidates(capture, node_def_provider=node_def)

        assert entries["positive_prompt"].required is True
        assert entries["negative_prompt"].node_id == "1"
        assert entries["negative_prompt"].input_name == "negative_prompt"
        assert entries["negative_prompt"].required is False

    def full_mapping_dict(self, prompt: dict | None = None) -> dict:
        return self.mapping_from_capture(make_capture(prompt or txt2img_prompt()))

    def default_values(self, prompt: dict | None = None) -> dict:
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

    def setup_mapped_workflow(self, workflow_id: str, prompt: dict | None = None):
        """workflow + version + mapping; returns (version_id, mapping_dict)."""
        version = self.create_version(workflow_id, prompt)
        mapping = self.full_mapping_dict(prompt)
        self.service.set_mapping(
            version["workflow_version_id"],
            entries=mapping["entries"],
            output_node_id=mapping["output_node_id"],
        )
        return version["workflow_version_id"], mapping


# ── Workflow ─────────────────────────────────────────────────────────────


class WorkflowTests(WorkflowDomainTestCase):
    def test_create_workflow_basic(self):
        wf = self.create_workflow(name="Krea Portrait Workflow")
        self.assertTrue(wf["workflow_id"].startswith("wf_"))
        self.assertEqual(wf["name"], "Krea Portrait Workflow")
        self.assertIn("created_at", wf)
        self.assertIn("updated_at", wf)
        self.assertEqual(self.service.get_workflow(wf["workflow_id"])["workflow_id"], wf["workflow_id"])

    def test_update_workflow_metadata(self):
        wf = self.create_workflow()
        updated = self.service.update_workflow(wf["workflow_id"], {
            "name": "Renamed", "description": "desc", "folder": "Portraits/AI",
            "tags": ["portrait", "krea"], "favorite": True,
            "source_url": "https://example.com/wf", "source_author": "Krea",
            "compatible_models": ["a.safetensors"],
        })
        self.assertEqual(updated["name"], "Renamed")
        self.assertEqual(updated["folder"], "Portraits/AI")
        self.assertEqual(updated["tags"], ["portrait", "krea"])
        self.assertTrue(updated["favorite"])
        self.assertEqual(updated["source_author"], "Krea")
        self.assertEqual(updated["compatible_models"], ["a.safetensors"])
        with self.assertRaises(WorkflowDomainValidationError):
            self.service.update_workflow(wf["workflow_id"], {"latest_version_id": "x"})

    def test_explicit_folders_are_durable_and_include_parents(self):
        self.service.create_folder(" /empty/ ")
        self.service.create_folder("nested/child")
        self.service.create_workflow("Legacy", folder="legacy/deep")

        self.assertEqual(
            self.service.list_folders(),
            ["empty", "legacy", "legacy/deep", "nested", "nested/child"],
        )
        with self.assertRaises(WorkflowDomainValidationError):
            self.service.create_folder(" /")
        with self.assertRaises(WorkflowDomainValidationError):
            self.service.create_folder(None)

        reloaded = WorkflowDomainService(self.root)
        self.assertEqual(reloaded.list_folders(), self.service.list_folders())


# ── Versions ─────────────────────────────────────────────────────────────


class VersionTests(WorkflowDomainTestCase):
    def test_create_version_numbering_and_dedupe(self):
        wf = self.create_workflow()
        v1 = self.create_version(wf["workflow_id"])
        self.assertEqual(v1["version_number"], 1)
        # Identical capture → dedupe, no new record.
        v1_again = self.create_version(wf["workflow_id"])
        self.assertEqual(v1_again["workflow_version_id"], v1["workflow_version_id"])
        self.assertEqual(len(self.service.store.list_versions()), 1)
        # Structural change → version 2.
        changed = txt2img_prompt()
        del changed["3"]["inputs"]["steps"]
        v2 = self.create_version(wf["workflow_id"], changed)
        self.assertEqual(v2["version_number"], 2)
        self.assertEqual(self.service.list_versions(wf["workflow_id"])[0]["version_number"], 1)
        latest = self.service.get_workflow(wf["workflow_id"])
        self.assertEqual(latest["latest_version_id"], v2["workflow_version_id"])

    def test_version_immutable_record(self):
        wf = self.create_workflow()
        v1 = self.create_version(wf["workflow_id"])
        before_raw = self.service.store.get_version(v1["workflow_version_id"])
        if before_raw is None:
            self.fail("version record missing after creation")
        before = copy.deepcopy(before_raw)
        changed = txt2img_prompt()
        changed["5"]["inputs"]["batch_size"] = 2
        self.create_version(wf["workflow_id"], changed)
        after_raw = self.service.store.get_version(v1["workflow_version_id"])
        if after_raw is None:
            self.fail("version record missing after creation")
        after = copy.deepcopy(after_raw)
        self.assertEqual(before, after)
        # No update/delete path exists on the store.
        self.assertFalse(hasattr(self.service.store, "update_version"))
        self.assertFalse(hasattr(self.service.store, "delete_version"))
        # Re-inserting the same id is refused.
        duplicate = WorkflowVersion.from_dict(after)
        with self.assertRaises(ImmutableVersionError):
            self.service.store.insert_version(duplicate)

    def test_graph_hash_changes_on_structure_change(self):
        wf = self.create_workflow()
        capture1 = make_capture(txt2img_prompt())
        v1 = self.create_version(wf["workflow_id"])
        self.assertEqual(v1["graph_hash"], graph_hash_from_capture(capture1))
        changed = txt2img_prompt()
        del changed["3"]["inputs"]["steps"]
        v2 = self.create_version(wf["workflow_id"], changed)
        self.assertNotEqual(v1["graph_hash"], v2["graph_hash"])
        # Cosmetic graph_json change with identical executable prompt → same hash.
        cosmetic = make_capture(txt2img_prompt(), graph_json={"id": "other", "nodes": []})
        self.assertEqual(
            graph_hash_from_capture(cosmetic),
            graph_hash_from_capture(capture1),
        )

    def test_incomplete_version_saved_but_unrunnable(self):
        wf = self.create_workflow()
        version = self.create_version(wf["workflow_id"])
        # Saved (present) but no mapping yet → incomplete, unrunnable.
        listed = self.service.get_version(version["workflow_version_id"])
        self.assertEqual(listed["state"]["status"], "incomplete")
        self.assertFalse(listed["state"]["runnable"])
        self.assertIn("missing mapping", listed["state"]["reasons"])
        with self.assertRaises(WorkflowNotRunnableError):
            self.service.assert_runnable(version["workflow_version_id"])

    def test_incomplete_version_missing_executable_prompt(self):
        wf = self.create_workflow()
        version = self.service.create_version_from_capture(
            wf["workflow_id"], make_capture({}, graph_json={"id": "empty"})
        )
        state = self.service.derive_version_state(version["workflow_version_id"])
        self.assertEqual(state.status, "incomplete")
        self.assertIn("no executable prompt", state.reasons)

    def test_version_with_mapping_becomes_ready(self):
        wf = self.create_workflow()
        version_id, mapping = self.setup_mapped_workflow(wf["workflow_id"])
        state = self.service.derive_version_state(version_id)
        self.assertEqual(state.status, "ready")
        self.assertTrue(state.runnable)
        self.service.assert_runnable(version_id)  # does not raise

class MappingTests(WorkflowDomainTestCase):
    def test_one_mapping_per_version(self):
        wf = self.create_workflow()
        version_id, mapping = self.setup_mapped_workflow(wf["workflow_id"])
        # A second mapping for the same version is REJECTED — the first
        # mapping is immutable. Change a mapping via create_mapping_revision.
        second = self.full_mapping_dict()
        second["entries"] = {"seed": second["entries"]["seed"]}
        with self.assertRaises(MappingAlreadyExistsError):
            self.service.set_mapping(
                version_id, entries=second["entries"],
                output_node_id=second["output_node_id"],
            )
        records = [
            m for m in self.service.store.list_mappings()
            if m.get("workflow_version_id") == version_id
        ]
        self.assertEqual(len(records), 1)
        self.assertEqual(
            set(records[0]["entries"][0].keys()), set(mapping["entries"]["seed"].keys()) | {
                "semantic_role", "node_id", "input_name", "output_name", "kind",
                "data_type", "enum_options", "minimum", "maximum", "step",
                "required", "multiline", "control_kind", "display_name",
            }
        )
        # The rejected replacement left the original mapping untouched.
        stored = self.service.get_mapping(version_id)
        if stored is None:
            self.fail("mapping missing after rejected replacement")
        self.assertEqual(stored["entries"][0]["semantic_role"], "positive_prompt")

    def test_mapping_candidates_derive_enum_metadata(self):
        capture = make_capture(txt2img_prompt())
        entries, output_node_id = derive_mapping_candidates(
            capture, node_def_provider=fake_node_def
        )
        self.assertEqual(output_node_id, "6")
        sampler = entries["sampler"]
        self.assertEqual(sampler.enum_options, ["euler", "dpmpp_2m"])
        self.assertEqual(sampler.control_kind, "enum")
        self.assertEqual(sampler.data_type, "ENUM")
        scheduler = entries["scheduler"]
        self.assertEqual(scheduler.enum_options, ["normal", "karras"])
        steps = entries["steps"]
        self.assertEqual(steps.control_kind, "integer")
        self.assertEqual(steps.minimum, 1.0)
        self.assertEqual(steps.maximum, 150.0)
        self.assertEqual(steps.step, 1.0)
        self.assertTrue(steps.required)
        model = entries["model"]
        self.assertEqual(model.enum_options, ["krea_model.safetensors", "flux-dev.safetensors"])
        self.assertEqual(model.node_id, "4")
        prompt_text = entries["positive_prompt"]
        self.assertEqual(prompt_text.control_kind, "multiline")
        self.assertTrue(prompt_text.multiline)
        width = entries["width"]
        self.assertEqual(width.minimum, 16.0)
        self.assertEqual(width.step, 8.0)
        # Connection specs are skipped.
        self.assertNotIn("clip", entries)
        self.assertNotIn("model_input", entries)


# ── Presets ──────────────────────────────────────────────────────────────


class MappingImmutabilityTests(WorkflowDomainTestCase):
    def test_mapping_cannot_be_replaced_for_existing_version(self):
        wf = self.create_workflow()
        version_id, mapping = self.setup_mapped_workflow(wf["workflow_id"])
        second = self.full_mapping_dict()
        with self.assertRaises(MappingAlreadyExistsError):
            self.service.set_mapping(
                version_id, entries=second["entries"],
                output_node_id=second["output_node_id"],
            )

    def test_old_mapping_deep_equal_after_rejected_replacement(self):
        wf = self.create_workflow()
        version_id, mapping = self.setup_mapped_workflow(wf["workflow_id"])
        before = copy.deepcopy(self.service.get_mapping(version_id))
        second = self.full_mapping_dict()
        del second["entries"]["steps"]
        with self.assertRaises(MappingAlreadyExistsError):
            self.service.set_mapping(
                version_id, entries=second["entries"],
                output_node_id=second["output_node_id"],
            )
        after = copy.deepcopy(self.service.get_mapping(version_id))
        self.assertEqual(before, after)
        records = [
            m for m in self.service.store.list_mappings()
            if m.get("workflow_version_id") == version_id
        ]
        self.assertEqual(len(records), 1)


# ── mapping revisions (hardening) ────────────────────────────────────────


class MappingRevisionTests(WorkflowDomainTestCase):
    def _revised_entries(self) -> dict:
        revised = self.full_mapping_dict()
        del revised["entries"]["steps"]
        return revised

    def test_mapping_revision_creates_new_version_same_graph(self):
        wf = self.create_workflow()
        v1_id, mapping = self.setup_mapped_workflow(wf["workflow_id"])
        v1 = self.service.get_version(v1_id)
        revised = self._revised_entries()
        v2 = self.service.create_mapping_revision(
            v1_id, entries=revised["entries"], output_node_id=revised["output_node_id"]
        )
        self.assertNotEqual(v2["workflow_version_id"], v1_id)
        self.assertEqual(v2["version_number"], 2)
        # Identical graph bytes allowed across versions — revision is intentional.
        self.assertEqual(v2["graph_hash"], v1["graph_hash"])
        self.assertEqual(v2["graph_json"], v1["graph_json"])
        self.assertEqual(v2["executable_prompt"], v1["executable_prompt"])
        versions = self.service.list_versions(wf["workflow_id"])
        self.assertEqual(len(versions), 2)
        self.assertEqual(
            [v["graph_hash"] for v in versions].count(v1["graph_hash"]), 2
        )
        # Latest version pointer moves to the revision.
        self.assertEqual(
            self.service.get_workflow(wf["workflow_id"])["latest_version_id"],
            v2["workflow_version_id"],
        )

    def test_old_version_keeps_old_mapping(self):
        wf = self.create_workflow()
        v1_id, mapping = self.setup_mapped_workflow(wf["workflow_id"])
        revised = self._revised_entries()
        v2 = self.service.create_mapping_revision(
            v1_id, entries=revised["entries"], output_node_id=revised["output_node_id"]
        )
        m1 = self.service.get_mapping(v1_id)
        m2 = self.service.get_mapping(v2["workflow_version_id"])
        if m1 is None or m2 is None:
            self.fail("mapping missing after revision")
        self.assertEqual(m1["workflow_version_id"], v1_id)
        self.assertEqual(m2["workflow_version_id"], v2["workflow_version_id"])
        self.assertNotEqual(m1["mapping_id"], m2["mapping_id"])
        roles1 = {e["semantic_role"] for e in m1["entries"]}
        roles2 = {e["semantic_role"] for e in m2["entries"]}
        self.assertIn("steps", roles1)
        self.assertNotIn("steps", roles2)
        # Old version still references its old mapping and stays ready.
        old = self.service.get_version(v1_id)
        self.assertEqual(old["mapping_id"], m1["mapping_id"])
        self.assertEqual(self.service.derive_version_state(v1_id).status, "ready")

    def test_capture_after_revision_dedupes_to_latest(self):
        wf = self.create_workflow()
        v1_id, mapping = self.setup_mapped_workflow(wf["workflow_id"])
        revised = self._revised_entries()
        v2 = self.service.create_mapping_revision(
            v1_id, entries=revised["entries"], output_node_id=revised["output_node_id"]
        )
        # An accidental re-capture of the same graph must NOT resurrect v1
        # or erase the revision — it dedupes to the latest version.
        again = self.create_version(wf["workflow_id"])
        self.assertEqual(again["workflow_version_id"], v2["workflow_version_id"])
        self.assertEqual(len(self.service.list_versions(wf["workflow_id"])), 2)

    def test_structural_graph_versioning_still_works(self):
        wf = self.create_workflow()
        v1_id, mapping = self.setup_mapped_workflow(wf["workflow_id"])
        changed = txt2img_prompt()
        del changed["3"]["inputs"]["steps"]
        v2 = self.create_version(wf["workflow_id"], changed)
        self.assertNotEqual(v2["workflow_version_id"], v1_id)
        self.assertEqual(v2["version_number"], 2)
        self.assertNotEqual(v2["graph_hash"], self.service.get_version(v1_id)["graph_hash"])
        v2_mapping = self.mapping_from_capture(make_capture(changed))
        self.service.set_mapping(
            v2["workflow_version_id"],
            entries=v2_mapping["entries"], output_node_id=v2_mapping["output_node_id"],
        )
        self.assertEqual(self.service.derive_version_state(v2["workflow_version_id"]).status, "ready")


# ── version-specific compatibility (hardening) ───────────────────────────


class VersionCompatTests(WorkflowDomainTestCase):
    def test_mapping_revision_captures_current_compatibility(self):
        wf = self.create_workflow(compatible_models=["flux-dev.safetensors"])
        v1_id, mapping = self.setup_mapped_workflow(wf["workflow_id"])
        self.service.update_workflow(
            wf["workflow_id"],
            {"compatible_models": ["flux-dev.safetensors", "krea_model.safetensors"]},
        )
        revised = self.full_mapping_dict()
        del revised["entries"]["steps"]
        v2 = self.service.create_mapping_revision(
            v1_id, entries=revised["entries"], output_node_id=revised["output_node_id"]
        )
        self.assertEqual(
            v2["compatible_models"], ["flux-dev.safetensors", "krea_model.safetensors"]
        )
        # Old version keeps the old frozen list.
        self.assertEqual(
            self.service.get_version(v1_id)["compatible_models"], ["flux-dev.safetensors"]
        )


# ── binding resolution (fail fast at save time, never at run time) ────


def linked_seed_prompt() -> dict:
    """KSampler seed wired to an upstream seed-producer node with no inputs.

    Mirrors the Krea 2 shape generically: node 204 holds its value only as
    widget/hidden state (empty executable inputs); node 163 consumes it via
    a connection spec.
    """
    return {
        "163": {"class_type": "KSampler", "inputs": {"seed": ["204", 0], "steps": 35}},
        "204": {"class_type": "SeedProducer", "inputs": {}},
        "199": {"class_type": "SaveImage", "inputs": {"images": ["163", 0]}},
    }


def linked_seed_ui_graph() -> dict:
    return {
        "id": "g-seed",
        "nodes": [
            {
                "id": 204,
                "type": "SeedProducer",
                "inputs": [],
                "outputs": [{"name": "seed", "type": "INT", "links": [241]}],
                "widgets_values": [{"seed": 953336612577361, "mode": "fixed"}],
            },
            {
                "id": 163,
                "type": "KSampler",
                "inputs": [
                    {"name": "seed", "type": "INT", "widget": {"name": "seed"}, "link": 241},
                    {"name": "steps", "type": "INT", "widget": {"name": "steps"}},
                ],
                "widgets_values": [35],
            },
        ],
        "links": [],
    }


def seed_producer_defs(class_type: str):
    if class_type == "SeedProducer":
        return ({}, {})
    return None


@pytest.mark.fast_unit
class BindingResolutionTests(WorkflowDomainTestCase):
    def test_resolver_accepts_plain_executable_input(self):
        target = resolve_binding_target(txt2img_prompt(), "3", "seed")
        self.assertTrue(target["resolvable"])
        self.assertEqual(target["location"], "inputs")
        self.assertFalse(target["linked"])
        self.assertTrue(target["node_present"])

    def test_resolver_accepts_linked_input_and_reports_upstream(self):
        target = resolve_binding_target(linked_seed_prompt(), "163", "seed")
        self.assertTrue(target["resolvable"])
        self.assertEqual(target["location"], "inputs")
        self.assertTrue(target["linked"])
        self.assertEqual(target["upstream_node_id"], "204")

    def test_resolver_rejects_widget_only_state(self):
        target = resolve_binding_target(
            linked_seed_prompt(),
            "204",
            "seed",
            ui_graph=linked_seed_ui_graph(),
            node_def_provider=seed_producer_defs,
        )
        self.assertFalse(target["resolvable"])
        self.assertTrue(target["node_present"])
        # The name exists, just never as an executable input.
        self.assertIn(target["location"], ("node_def", "ui_widget"))

    def test_resolver_reports_missing_node(self):
        target = resolve_binding_target(linked_seed_prompt(), "999", "seed")
        self.assertFalse(target["resolvable"])
        self.assertFalse(target["node_present"])
        self.assertIsNone(target["location"])

    def test_candidates_suggest_downstream_consumer(self):
        candidates = find_binding_candidates(linked_seed_prompt(), "seed")
        self.assertTrue(candidates)
        first = candidates[0]
        self.assertEqual(first["node_id"], "163")
        self.assertEqual(first["input_name"], "seed")
        self.assertEqual(first["via"], "inputs")
        self.assertTrue(first["linked"])
        self.assertEqual(first["upstream_node_id"], "204")

    def test_set_mapping_rejects_unresolvable_binding(self):
        wf = self.create_workflow()
        version = self.create_version(wf["workflow_id"], linked_seed_prompt())
        bad = {
            "seed": {
                "semantic_role": "seed",
                "node_id": "204",
                "input_name": "seed",
                "kind": "widget",
                "control_kind": "integer",
                "display_name": "Seed",
            }
        }
        with self.assertRaises(WorkflowDomainValidationError) as ctx:
            self.service.set_mapping(
                version["workflow_version_id"], entries=bad, output_node_id="199"
            )
        message = str(ctx.exception)
        self.assertIn("'seed'", message)
        self.assertIn("204", message)
        # Points at the fix, not just the failure.
        self.assertIn("163", message)
        # Nothing persisted.
        self.assertIsNone(
            self.service.store.get_mapping_for_version(version["workflow_version_id"])
        )

    def test_set_mapping_rejects_node_output_binding_for_input_role(self):
        # Regression: a prompt row captured from a node *output* (empty
        # input_name, kind node_output) passed save-time validation and
        # failed every run with "mapped control 'prompt' has no node/input
        # binding". Mapping entries bind values INTO inputs; outputs are
        # never valid here.
        wf = self.create_workflow()
        version = self.create_version(wf["workflow_id"], linked_seed_prompt())
        bad = {
            "prompt": {
                "semantic_role": "prompt",
                "node_id": "204",
                "input_name": "",
                "kind": "node_output",
                "control_kind": "multiline",
                "display_name": "Prompt",
            }
        }
        with self.assertRaises(WorkflowDomainValidationError) as ctx:
            self.service.set_mapping(
                version["workflow_version_id"], entries=bad, output_node_id="199"
            )
        message = str(ctx.exception)
        self.assertIn("'prompt'", message)
        self.assertIn("node output", message)
        # Nothing persisted.
        self.assertIsNone(
            self.service.store.get_mapping_for_version(version["workflow_version_id"])
        )

    def test_set_mapping_accepts_linked_downstream_binding(self):
        wf = self.create_workflow()
        version = self.create_version(wf["workflow_id"], linked_seed_prompt())
        good = {
            "seed": {
                "semantic_role": "seed",
                "node_id": "163",
                "input_name": "seed",
                "kind": "node",
                "control_kind": "integer",
                "display_name": "Seed",
            }
        }
        self.service.set_mapping(
            version["workflow_version_id"], entries=good, output_node_id="199"
        )
        state = self.service.derive_version_state(version["workflow_version_id"])
        self.assertEqual(state.status, "ready")
        self.assertTrue(state.runnable)

    def test_mapping_revision_rejects_unresolvable_binding(self):
        wf = self.create_workflow()
        version_id, _ = self.setup_mapped_workflow(wf["workflow_id"])
        prompt = self.service.get_version(version_id)["executable_prompt"]
        bad_seed = {
            "semantic_role": "seed",
            "node_id": "nope",
            "input_name": "seed",
            "kind": "widget",
            "control_kind": "integer",
            "display_name": "Seed",
        }
        entries = {
            role: e.to_dict()
            for role, e in derive_mapping_candidates(
                make_capture(prompt), node_def_provider=fake_node_def
            )[0].items()
        }
        entries["seed"] = bad_seed
        before = len(self.service.store.list_versions_for_workflow(wf["workflow_id"]))
        with self.assertRaises(WorkflowDomainValidationError):
            self.service.create_mapping_revision(
                version_id, entries=entries, output_node_id="6"
            )
        # Rejected before any new version record.
        self.assertEqual(
            len(self.service.store.list_versions_for_workflow(wf["workflow_id"])), before
        )

    def test_gating_flags_unresolvable_node_kind_binding(self):
        wf = self.create_workflow()
        version = self.create_version(wf["workflow_id"], linked_seed_prompt())
        version_id = version["workflow_version_id"]
        bad_mapping = Mapping(
            mapping_id="wm_testbad00000001",
            workflow_version_id=version_id,
            output_node_id="199",
            entries={
                "seed": MappingEntry(
                    semantic_role="seed",
                    node_id="204",
                    input_name="seed",
                    kind="node",
                )
            },
        )
        self.service.store.insert_mapping(bad_mapping)
        state = self.service.derive_version_state(version_id)
        self.assertEqual(state.status, "incomplete")
        self.assertFalse(state.runnable)
        self.assertIn(
            "mapped entry 'seed' input 'seed' not present on node 204", state.reasons
        )


def _subgraph_fixture() -> tuple[dict, dict]:
    """Minimal outer-container + expanded-prompt subgraph fixture.

    Outer node ``30`` (subgraph ``sg-1``) exposes widgets that feed inner
    nodes through ``inputNode`` links; ComfyUI expands them to ``"30:<inner>"``
    prompt keys. Mirrors the real Krea subgraph shape at a fraction of the
    size.
    """
    sg_id = "sg-1"
    graph_json = {
        "nodes": [
            {
                "id": 30,
                "type": sg_id,
                "inputs": [
                    {"name": "value", "type": "STRING", "widget": {"name": "value"}, "link": None},
                    {"name": "seed_1", "type": "INT", "widget": {"name": "seed_1"}, "link": None},
                    {"name": "unet_name", "type": "COMBO", "widget": {"name": "unet_name"}, "link": None},
                ],
                "outputs": [{"name": "IMAGE", "type": "IMAGE", "links": [44]}],
                "widgets_values": ["hello", 7, "model.safetensors"],
            },
            {
                "id": 29,
                "type": "SaveImage",
                "inputs": [{"name": "images", "type": "IMAGE", "link": 44}],
                "outputs": [],
            },
        ],
        "links": [[44, 30, 0, 29, 0, "IMAGE"]],
        "definitions": {
            "subgraphs": [
                {
                    "id": sg_id,
                    "inputNode": {"id": -10},
                    "outputNode": {"id": -20},
                    "nodes": [
                        {
                            "id": 19,
                            "type": "PrimitiveStringMultiline",
                            "inputs": [{"name": "value", "type": "STRING", "widget": {"name": "value"}, "link": 45}],
                            "widgets_values": ["hello"],
                        },
                        {
                            "id": 3,
                            "type": "KSampler",
                            "inputs": [
                                {"name": "model", "type": "MODEL", "link": 30},
                                {"name": "seed", "type": "INT", "widget": {"name": "seed"}, "link": 77},
                            ],
                            "widgets_values": [7],
                        },
                        {
                            "id": 10,
                            "type": "UNETLoader",
                            "inputs": [{"name": "unet_name", "type": "COMBO", "widget": {"name": "unet_name"}, "link": 82}],
                            "widgets_values": ["model.safetensors"],
                        },
                    ],
                    "links": [
                        {"id": 45, "origin_id": -10, "origin_slot": 0, "target_id": 19, "target_slot": 0, "type": "STRING"},
                        {"id": 77, "origin_id": -10, "origin_slot": 1, "target_id": 3, "target_slot": 1, "type": "INT"},
                        {"id": 82, "origin_id": -10, "origin_slot": 2, "target_id": 10, "target_slot": 0, "type": "COMBO"},
                    ],
                }
            ]
        },
    }
    prompt = {
        "30:19": {"class_type": "PrimitiveStringMultiline", "inputs": {"value": "hello"}},
        "30:3": {"class_type": "KSampler", "inputs": {"model": ["30:10", 0], "seed": 7}},
        "30:10": {"class_type": "UNETLoader", "inputs": {"unet_name": "model.safetensors"}},
        "29": {"class_type": "SaveImage", "inputs": {"images": ["30:3", 0]}},
    }
    return graph_json, prompt


@pytest.mark.fast_unit
class SubgraphBindingTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.service = WorkflowDomainService(str(Path(self._tmp.name)))

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_outer_widget_resolves_to_expanded(self):
        graph_json, prompt = _subgraph_fixture()
        target = resolve_binding_target(
            prompt, "30", "value", ui_graph=graph_json
        )
        self.assertTrue(target.get("resolvable"))
        self.assertEqual(target.get("expanded_node_id"), "30:19")
        self.assertEqual(target.get("expanded_input_name"), "value")

    def test_inner_local_resolves_to_expanded(self):
        graph_json, prompt = _subgraph_fixture()
        target = resolve_binding_target(
            prompt, "10", "unet_name", ui_graph=graph_json
        )
        self.assertTrue(target.get("resolvable"))
        self.assertEqual(target.get("expanded_node_id"), "30:10")

    def test_save_normalizes_subgraph_bindings_to_expanded(self):
        graph_json, prompt = _subgraph_fixture()
        wf = self.service.create_workflow("Subgraph")
        version = self.service.create_version_from_capture(
            wf["workflow_id"],
            {"graph_json": graph_json, "api_prompt_json": {"workflow": {}, "output": prompt}},
        )
        version_id = version["workflow_version_id"]
        mapping = self.service.set_mapping(
            version_id,
            entries={
                "prompt": {"semantic_role": "prompt", "node_id": "30", "input_name": "value", "kind": "widget", "control_kind": "multiline", "display_name": "Prompt"},
                "seed": {"semantic_role": "seed", "node_id": "30", "input_name": "seed_1", "kind": "widget", "control_kind": "integer", "display_name": "Seed"},
                "model_unet": {"semantic_role": "model_unet", "node_id": "10", "input_name": "unet_name", "kind": "widget", "control_kind": "file", "display_name": "UNET"},
            },
            output_node_id="29",
        )
        stored = {e["semantic_role"]: e for e in mapping["entries"]}
        self.assertEqual(stored["prompt"]["node_id"], "30:19")
        self.assertEqual(stored["prompt"]["input_name"], "value")
        self.assertEqual(stored["seed"]["node_id"], "30:3")
        self.assertEqual(stored["seed"]["input_name"], "seed")
        self.assertEqual(stored["model_unet"]["node_id"], "30:10")
        state = self.service.derive_version_state(version_id)
        self.assertTrue(state.runnable, state.reasons)

    def test_ambiguous_inner_reports_subgraph_hint(self):
        graph_json, prompt = _subgraph_fixture()
        prompt = dict(prompt)
        prompt["31:10"] = {"class_type": "UNETLoader", "inputs": {"unet_name": "other.safetensors"}}
        target = resolve_binding_target(
            prompt, "10", "unet_name", ui_graph=graph_json
        )
        self.assertFalse(target.get("resolvable"))
        self.assertIn("31:10", target.get("subgraph_candidates") or [])


@pytest.mark.fast_unit
class ReferenceDiscoveryTests(WorkflowDomainTestCase):
    """Phase 8 Lane A: structural reference discovery + version-bound bindings.

    Covers fixed/single/autogrow capacity, numeric slot ordering (10 after
    2), reserved I2I source sockets, multi-candidate confirmation, stale /
    subgraph-ambiguous binding rejection, class-rename invariance, Method-2
    chain recognition, and fail-closed generic-T2I incompatibility. No
    Torch, model, or Modal access.
    """

    def _node_defs(self, extra=None):
        base = {
            "RefConditioner": (
                {
                    "clip": ("CLIP",),
                    "text": ("STRING", {"multiline": True}),
                    "image": ("IMAGE",),
                },
                {},
            ),
            "CLIPLoader": ({"clip_name": ("STRING",)}, {}),
            "LoadImage": ({"image": ("STRING",)}, {}),
            "VAELoader": ({"vae_name": ("STRING",)}, {}),
            "VAEEncode": ({"pixels": ("IMAGE",), "vae": ("VAE",)}, {}),
            "ReferenceLatent": (
                {"latent": ("LATENT",), "conditioning": ("CONDITIONING",)},
                {},
            ),
            "KSampler": (
                {"model": ("MODEL",), "positive": ("CONDITIONING",),
                 "negative": ("CONDITIONING",), "latent_image": ("LATENT",)},
                {},
            ),
            "SaveImage": ({"images": ("IMAGE",)}, {}),
        }
        if extra:
            base.update(extra)
        def provider(class_type):
            return base.get(str(class_type))
        return provider

    def _returns(self, mapping):
        def provider(class_type):
            return mapping.get(str(class_type))
        return provider

    def _method1_prompt(self):
        return {
            "1": {"class_type": "CLIPLoader", "inputs": {"clip_name": "c.safetensors"}},
            "2": {"class_type": "LoadImage", "inputs": {"image": "a.png"}},
            "3": {"class_type": "RefConditioner", "inputs": {
                "clip": ["1", 0], "text": "a cat", "image": ["2", 0]}},
            "4": {"class_type": "KSampler", "inputs": {
                "model": ["9", 0], "positive": ["3", 0],
                "negative": ["3", 0], "latent_image": ["5", 0]}},
            "5": {"class_type": "EmptyLatentImage",
                   "inputs": {"width": 512, "height": 512, "batch_size": 1}},
            "6": {"class_type": "SaveImage", "inputs": {"images": ["4", 0]}},
            "9": {"class_type": "UNETLoader", "inputs": {"unet_name": "u.safetensors"}},
        }

    def test_single_capacity_unique_candidate(self):
        from studio_domain.graph import discover_reference_candidates
        prompt = self._method1_prompt()
        out = discover_reference_candidates(
            prompt,
            node_def_provider=self._node_defs(),
            return_types_provider=self._returns({"RefConditioner": ["CONDITIONING"]}),
            output_node_id="6",
        )
        self.assertEqual(out["resolution"], "unique")
        self.assertEqual(len(out["candidates"]), 1)
        cand = out["candidates"][0]
        self.assertEqual(cand["method"], "conditioning_slots")
        self.assertEqual(cand["node_id"], "3")
        self.assertEqual(cand["capacity"]["kind"], "single")
        self.assertEqual(cand["capacity"]["reference_writable"], 1)
        self.assertTrue(cand["compatible"])

    def test_optional_unlinked_slots_are_bindable_capacity(self):
        # Fixed three-slot node (Qwen Plus shape): image1 wired, image2/3
        # declared optional and unlinked. Optional omission must not block —
        # the candidate stays compatible with capacity 3 (1 evidenced +
        # 2 bound at run time via isolated loader branches).
        from studio_domain.graph import discover_reference_candidates
        extra = {
            "TrioRef": (
                {
                    "clip": ("CLIP",),
                    "text": ("STRING",),
                },
                {
                    "image1": ("IMAGE",),
                    "image2": ("IMAGE",),
                    "image3": ("IMAGE",),
                },
            ),
        }
        prompt = {
            "1": {"class_type": "CLIPLoader", "inputs": {"clip_name": "c.safetensors"}},
            "2": {"class_type": "LoadImage", "inputs": {"image": "a.png"}},
            "3": {"class_type": "TrioRef", "inputs": {
                "clip": ["1", 0], "text": "edit this", "image1": ["2", 0]}},
            "4": {"class_type": "KSampler", "inputs": {
                "model": ["9", 0], "positive": ["3", 0],
                "negative": ["3", 0], "latent_image": ["5", 0]}},
            "5": {"class_type": "EmptyLatentImage",
                   "inputs": {"width": 512, "height": 512, "batch_size": 1}},
            "6": {"class_type": "SaveImage", "inputs": {"images": ["4", 0]}},
            "9": {"class_type": "UNETLoader", "inputs": {"unet_name": "u.safetensors"}},
        }
        out = discover_reference_candidates(
            prompt,
            node_def_provider=self._node_defs(extra),
            return_types_provider=self._returns({"TrioRef": ["CONDITIONING"]}),
            output_node_id="6",
        )
        cands = [c for c in out["candidates"] if c["node_id"] == "3"]
        self.assertEqual(len(cands), 1)
        cand = cands[0]
        self.assertTrue(cand["compatible"])
        self.assertEqual(cand["capacity"]["count"], 3)
        self.assertEqual(cand["capacity"]["reference_writable"], 3)
        by_socket = {s["socket"]: s for s in cand["slots"]}
        self.assertTrue(by_socket["image1"]["resolvable"])
        self.assertFalse(by_socket["image2"]["resolvable"])
        self.assertTrue(by_socket["image2"]["writable"])
        self.assertFalse(by_socket["image2"].get("required"))
        self.assertEqual(out["resolution"], "unique")

    def test_required_unlinked_slot_still_blocks(self):
        # Same shape but image2 declared required and unlinked: the
        # candidate must stay incompatible (nothing invented).
        from studio_domain.graph import discover_reference_candidates
        extra = {
            "DuoRef": (
                {
                    "clip": ("CLIP",),
                    "text": ("STRING",),
                    "image2": ("IMAGE",),
                },
                {
                    "image1": ("IMAGE",),
                },
            ),
        }
        prompt = {
            "1": {"class_type": "CLIPLoader", "inputs": {"clip_name": "c.safetensors"}},
            "2": {"class_type": "LoadImage", "inputs": {"image": "a.png"}},
            "3": {"class_type": "DuoRef", "inputs": {
                "clip": ["1", 0], "text": "edit this", "image1": ["2", 0]}},
            "4": {"class_type": "KSampler", "inputs": {
                "model": ["9", 0], "positive": ["3", 0],
                "negative": ["3", 0], "latent_image": ["5", 0]}},
            "5": {"class_type": "EmptyLatentImage",
                   "inputs": {"width": 512, "height": 512, "batch_size": 1}},
            "6": {"class_type": "SaveImage", "inputs": {"images": ["4", 0]}},
            "9": {"class_type": "UNETLoader", "inputs": {"unet_name": "u.safetensors"}},
        }
        out = discover_reference_candidates(
            prompt,
            node_def_provider=self._node_defs(extra),
            return_types_provider=self._returns({"DuoRef": ["CONDITIONING"]}),
            output_node_id="6",
        )
        self.assertEqual(out["candidates"], [])
        bad = [c for c in out["incompatible"] if c.get("node_id") == "3"]
        self.assertEqual(len(bad), 1)
        self.assertTrue(any("image2" in r for r in bad[0]["reasons"]))

    def test_numeric_ordering_ten_after_two(self):
        from studio_domain.graph import discover_reference_candidates
        extra = {
            "MultiRef": (
                {
                    "clip": ("CLIP",),
                    "text": ("STRING",),
                    "image_2": ("IMAGE",),
                    "image_10": ("IMAGE",),
                    "image_1": ("IMAGE",),
                },
                {},
            ),
        }
        prompt = {
            "1": {"class_type": "CLIPLoader", "inputs": {"clip_name": "c"}},
            "2": {"class_type": "MultiRef", "inputs": {
                "clip": ["1", 0], "text": "x",
                "image_2": ["7", 0], "image_10": ["7", 0], "image_1": ["7", 0]}},
            "3": {"class_type": "KSampler", "inputs": {
                "model": ["9", 0], "positive": ["2", 0],
                "negative": ["2", 0], "latent_image": ["5", 0]}},
            "5": {"class_type": "EmptyLatentImage",
                   "inputs": {"width": 64, "height": 64, "batch_size": 1}},
            "6": {"class_type": "SaveImage", "inputs": {"images": ["3", 0]}},
            "7": {"class_type": "LoadImage", "inputs": {"image": "a.png"}},
            "9": {"class_type": "UNETLoader", "inputs": {"unet_name": "u"}},
        }
        out = discover_reference_candidates(
            prompt,
            node_def_provider=self._node_defs(extra),
            return_types_provider=self._returns({"MultiRef": ["CONDITIONING"]}),
            output_node_id="6",
        )
        cands = [c for c in out["candidates"] if c["node_id"] == "2"]
        self.assertEqual(len(cands), 1)
        self.assertEqual(cands[0]["slot_order"], ["image_1", "image_2", "image_10"])
        self.assertEqual(cands[0]["capacity"]["kind"], "fixed")

    def test_autogrow_capacity_from_schema(self):
        from studio_domain.graph import discover_reference_candidates
        extra = {
            "GrowRef": (
                {
                    "clip": ("CLIP",),
                    "text": ("STRING",),
                    "image": ("IMAGE", {"autogrow": True, "max": 4}),
                },
                {},
            ),
        }
        prompt = {
            "1": {"class_type": "CLIPLoader", "inputs": {"clip_name": "c"}},
            "2": {"class_type": "GrowRef", "inputs": {
                "clip": ["1", 0], "text": "x", "image": ["7", 0]}},
            "3": {"class_type": "KSampler", "inputs": {
                "model": ["9", 0], "positive": ["2", 0],
                "negative": ["2", 0], "latent_image": ["5", 0]}},
            "5": {"class_type": "EmptyLatentImage",
                   "inputs": {"width": 64, "height": 64, "batch_size": 1}},
            "6": {"class_type": "SaveImage", "inputs": {"images": ["3", 0]}},
            "7": {"class_type": "LoadImage", "inputs": {"image": "a.png"}},
            "9": {"class_type": "UNETLoader", "inputs": {"unet_name": "u"}},
        }
        out = discover_reference_candidates(
            prompt,
            node_def_provider=self._node_defs(extra),
            return_types_provider=self._returns({"GrowRef": ["CONDITIONING"]}),
            output_node_id="6",
        )
        cands = [c for c in out["candidates"] if c["node_id"] == "2"]
        self.assertEqual(len(cands), 1)
        self.assertEqual(cands[0]["capacity"]["kind"], "autogrow")
        self.assertEqual(cands[0]["capacity"]["max"], 4)

    def test_reserved_source_socket_excluded(self):
        from studio_domain.graph import discover_reference_candidates
        extra = {
            "DualRef": (
                {
                    "clip": ("CLIP",),
                    "text": ("STRING",),
                    "image_1": ("IMAGE",),
                    "image_2": ("IMAGE",),
                },
                {},
            ),
        }
        prompt = {
            "1": {"class_type": "CLIPLoader", "inputs": {"clip_name": "c"}},
            "2": {"class_type": "DualRef", "inputs": {
                "clip": ["1", 0], "text": "x",
                "image_1": ["7", 0], "image_2": ["8", 0]}},
            "3": {"class_type": "KSampler", "inputs": {
                "model": ["9", 0], "positive": ["2", 0],
                "negative": ["2", 0], "latent_image": ["5", 0]}},
            "5": {"class_type": "EmptyLatentImage",
                   "inputs": {"width": 64, "height": 64, "batch_size": 1}},
            "6": {"class_type": "SaveImage", "inputs": {"images": ["3", 0]}},
            "7": {"class_type": "LoadImage", "inputs": {"image": "a.png"}},
            "8": {"class_type": "LoadImage", "inputs": {"image": "b.png"}},
            "9": {"class_type": "UNETLoader", "inputs": {"unet_name": "u"}},
        }
        out = discover_reference_candidates(
            prompt,
            node_def_provider=self._node_defs(extra),
            return_types_provider=self._returns({"DualRef": ["CONDITIONING"]}),
            output_node_id="6",
            prompt_bindings={"source_image": {"node_id": "2", "input_name": "image_1"}},
        )
        cands = [c for c in out["candidates"] if c["node_id"] == "2"]
        self.assertEqual(len(cands), 1)
        kinds = {s["socket"]: s["kind"] for s in cands[0]["slots"]}
        self.assertEqual(kinds["image_1"], "source")
        self.assertEqual(kinds["image_2"], "reference")
        self.assertEqual(cands[0]["capacity"]["reference_writable"], 1)

    def test_multi_candidate_requires_confirmation(self):
        from studio_domain.graph import discover_reference_candidates
        prompt = {
            "1": {"class_type": "CLIPLoader", "inputs": {"clip_name": "c"}},
            "2": {"class_type": "RefConditioner", "inputs": {
                "clip": ["1", 0], "text": "x", "image": ["7", 0]}},
            "3": {"class_type": "RefConditioner", "inputs": {
                "clip": ["1", 0], "text": "y", "image": ["7", 0]}},
            "4": {"class_type": "KSampler", "inputs": {
                "model": ["9", 0], "positive": ["2", 0],
                "negative": ["2", 0], "latent_image": ["5", 0]}},
            "10": {"class_type": "KSampler", "inputs": {
                "model": ["9", 0], "positive": ["3", 0],
                "negative": ["3", 0], "latent_image": ["4", 0]}},
            "6": {"class_type": "SaveImage", "inputs": {"images": ["10", 0]}},
            "7": {"class_type": "LoadImage", "inputs": {"image": "a.png"}},
            "9": {"class_type": "UNETLoader", "inputs": {"unet_name": "u"}},
            "5": {"class_type": "EmptyLatentImage",
                   "inputs": {"width": 64, "height": 64, "batch_size": 1}},
        }
        out = discover_reference_candidates(
            prompt,
            node_def_provider=self._node_defs(),
            return_types_provider=self._returns({"RefConditioner": ["CONDITIONING"]}),
            output_node_id="6",
        )
        self.assertEqual(out["resolution"], "unresolved")
        self.assertGreaterEqual(len(out["candidates"]), 2)
        # Saving without an explicit candidate pick must fail.
        service = WorkflowDomainService(self.root)
        service._node_def_provider = self._node_defs()
        wf = service.create_workflow("ref")
        version = service.create_version_from_capture(
            wf["workflow_id"], make_capture(prompt))
        entries, output_id = derive_mapping_candidates(
            make_capture(prompt), node_def_provider=fake_node_def)
        with self.assertRaises(WorkflowDomainValidationError):
            service.set_mapping(
                version["workflow_version_id"],
                entries={r: e.to_dict() for r, e in entries.items()},
                output_node_id=output_id or "6",
                reference_method="conditioning_slots",
                reference_bindings={"slots": [
                    {"node_id": "2", "socket": "image", "order": 0}]},
            )

    def test_stale_reference_binding_blocks(self):
        service = WorkflowDomainService(self.root)
        service._node_def_provider = self._node_defs()
        wf = service.create_workflow("ref")
        prompt = self._method1_prompt()
        version = service.create_version_from_capture(
            wf["workflow_id"], make_capture(prompt))
        entries, output_id = derive_mapping_candidates(
            make_capture(prompt), node_def_provider=fake_node_def)
        with self.assertRaises(WorkflowDomainValidationError):
            service.set_mapping(
                version["workflow_version_id"],
                entries={r: e.to_dict() for r, e in entries.items()},
                output_node_id=output_id or "6",
                reference_method="conditioning_slots",
                reference_bindings={"slots": [
                    {"node_id": "999", "socket": "image", "order": 0}]},
            )

    def test_renamed_classes_do_not_change_discovery(self):
        from studio_domain.graph import discover_reference_candidates
        renamed_defs = self._node_defs()
        prompt_a = self._method1_prompt()
        prompt_b = {
            nid: {"class_type": ("RenamedLoader" if n["class_type"] == "LoadImage" else n["class_type"]),
                   "inputs": dict(n["inputs"])}
            for nid, n in prompt_a.items()
        }
        def renamed_provider(class_type):
            if class_type == "RenamedLoader":
                return ({"image": ("STRING",)}, {})
            return renamed_defs(class_type)
        returns = self._returns({"RefConditioner": ["CONDITIONING"]})
        out_a = discover_reference_candidates(
            prompt_a, node_def_provider=self._node_defs(),
            return_types_provider=returns, output_node_id="6")
        out_b = discover_reference_candidates(
            prompt_b, node_def_provider=renamed_provider,
            return_types_provider=returns, output_node_id="6")
        self.assertEqual(len(out_a["candidates"]), len(out_b["candidates"]))
        self.assertEqual(out_a["resolution"], out_b["resolution"])

    def test_method2_chain_recognized(self):
        from studio_domain.graph import discover_reference_candidates
        prompt = {
            "1": {"class_type": "CLIPLoader", "inputs": {"clip_name": "c"}},
            "2": {"class_type": "CLIPTextEncode",
                   "inputs": {"text": "x", "clip": ["1", 0]}},
            "7": {"class_type": "LoadImage", "inputs": {"image": "r.png"}},
            "8": {"class_type": "VAELoader", "inputs": {"vae_name": "v"}},
            "9": {"class_type": "VAEEncode", "inputs": {
                "pixels": ["7", 0], "vae": ["8", 0]}},
            "10": {"class_type": "ReferenceLatent", "inputs": {
                "latent": ["9", 0], "conditioning": ["2", 0]}},
            "4": {"class_type": "KSampler", "inputs": {
                "model": ["11", 0], "positive": ["2", 0],
                "negative": ["2", 0], "latent_image": ["10", 0]}},
            "6": {"class_type": "SaveImage", "inputs": {"images": ["4", 0]}},
            "11": {"class_type": "UNETLoader", "inputs": {"unet_name": "u"}},
        }
        out = discover_reference_candidates(
            prompt,
            node_def_provider=self._node_defs(),
            output_node_id="6",
        )
        chains = [c for c in out["candidates"] if c["method"] == "reference_latent_chain"]
        self.assertEqual(len(chains), 1)
        chain = chains[0]["chain"]
        self.assertEqual(chain["loader_node_id"], "7")
        self.assertEqual(chain["vae_encode_node_id"], "9")
        self.assertEqual(chain["reference_latent_node_id"], "10")
        self.assertIn("10", chain["order"][-2])

    def test_generic_t2i_without_evidence_is_incompatible(self):
        from studio_domain.graph import discover_reference_candidates
        out = discover_reference_candidates(
            txt2img_prompt(),
            node_def_provider=fake_node_def,
            output_node_id="6",
        )
        self.assertEqual(out["candidates"], [])
        self.assertEqual(out["resolution"], "incompatible")
        self.assertTrue(out["incompatible"])

    def test_mapping_persists_reference_and_companion(self):
        service = WorkflowDomainService(self.root)
        svc_defs = self._node_defs()
        service._node_def_provider = svc_defs
        wf = service.create_workflow("ref")
        prompt = self._method1_prompt()
        version = service.create_version_from_capture(
            wf["workflow_id"], make_capture(prompt))
        entries, output_id = derive_mapping_candidates(
            make_capture(prompt), node_def_provider=fake_node_def)
        mapping = service.set_mapping(
            version["workflow_version_id"],
            entries={r: e.to_dict() for r, e in entries.items()},
            output_node_id=output_id or "6",
            reference_method="conditioning_slots",
            reference_bindings={
                "candidate_id": "conditioning_slots:3",
                "slots": [{"node_id": "3", "socket": "image", "order": 0}],
            },
        )
        self.assertEqual(mapping["reference_method"], "conditioning_slots")
        companion = service.build_studio_references(version["workflow_version_id"])
        self.assertEqual(companion["method"], "conditioning_slots")
        self.assertEqual(
            companion["origin_version_id"], version["workflow_version_id"])
        self.assertEqual(companion["origin_workflow_id"], wf["workflow_id"])
        self.assertIn("3:image", companion["card_ids"])
        self.assertNotIn("executable_prompt", companion)


@pytest.mark.fast_unit
class UniversalOutputDiscoveryTests(unittest.TestCase):
    """Universal final-image capture: every image-bearing node is found.

    Covers the fixed allowlist (no registry needed), custom compare/preview
    classes via RETURN_TYPES (RGThree-style, Pixaroma-style), graph-order
    collection, explicit-output hoisting, and the capture wrapper.
    """

    def _returns_provider(self, mapping):
        def provider(class_type):
            return mapping.get(str(class_type))
        return provider

    def _prompt(self):
        return {
            "1": {"class_type": "KSampler", "inputs": {"model": ["4", 0]}},
            "2": {"class_type": "SaveImage", "inputs": {"images": ["1", 0]}},
            "3": {"class_type": "RGThreeImageCompare",
                   "inputs": {"image_a": ["1", 0], "image_b": ["1", 0]}},
            "4": {"class_type": "PixaromaPreview", "inputs": {"images": ["1", 0]}},
            "5": {"class_type": "CLIPTextEncode", "inputs": {"text": "x"}},
        }

    def _mapping(self):
        return {
            "SaveImage": ["IMAGE"],
            "RGThreeImageCompare": ["IMAGE", "IMAGE"],
            "PixaromaPreview": ["IMAGE"],
            "KSampler": ["LATENT"],
            "CLIPTextEncode": ["CONDITIONING"],
        }

    def test_allowlist_class_needs_no_registry(self):
        self.assertTrue(node_has_image_output("SaveImage"))
        self.assertTrue(node_has_image_output("PreviewImage"))
        self.assertTrue(node_has_image_output("SaveImageWithMetaData"))

    def test_custom_image_class_discovered_via_provider(self):
        provider = self._returns_provider(self._mapping())
        self.assertTrue(node_has_image_output(
            "RGThreeImageCompare", return_types_provider=provider))
        self.assertTrue(node_has_image_output(
            "PixaromaPreview", return_types_provider=provider))

    def test_non_image_class_rejected(self):
        provider = self._returns_provider(self._mapping())
        self.assertFalse(node_has_image_output(
            "KSampler", return_types_provider=provider))
        self.assertFalse(node_has_image_output(
            "NoSuchClass", return_types_provider=provider))
        self.assertFalse(node_has_image_output(""))
        self.assertFalse(node_has_image_output("NoSuchClass"))

    def test_collects_all_in_graph_order(self):
        ids = derive_output_node_ids_from_prompt(
            self._prompt(),
            return_types_provider=self._returns_provider(self._mapping()),
        )
        self.assertEqual(ids, ["2", "3", "4"])

    def test_explicit_output_hoisted_first(self):
        ids = derive_output_node_ids_from_prompt(
            self._prompt(),
            explicit_output_id="4",
            return_types_provider=self._returns_provider(self._mapping()),
        )
        self.assertEqual(ids, ["4", "2", "3"])

    def test_capture_wrapper_matches(self):
        capture = {"graph_json": {"id": "g1", "nodes": []},
                   "api_prompt_json": {"workflow": {}, "output": self._prompt()}}
        ids = derive_output_node_ids(
            capture,
            return_types_provider=self._returns_provider(self._mapping()),
        )
        self.assertEqual(ids, ["2", "3", "4"])


if __name__ == "__main__":
    unittest.main()


if __name__ == "__main__":
    unittest.main()
