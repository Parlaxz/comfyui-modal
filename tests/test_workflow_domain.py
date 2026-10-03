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

from studio_domain import (
    ImmutableVersionError,
    MappingAlreadyExistsError,
    WorkflowDomainService,
    WorkflowNotRunnableError,
    WorkflowDomainValidationError,
    WorkflowVersion,
    derive_mapping_candidates,
    graph_hash_from_capture,
)
from studio_domain.services import WorkflowDomainService as _Service  # noqa: F401


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


if __name__ == "__main__":
    unittest.main()
