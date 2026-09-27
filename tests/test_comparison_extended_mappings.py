import importlib.util
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
COMPARISON_PATH = REPO_ROOT / "comparison.py"


def load_comparison():
    if not COMPARISON_PATH.exists():
        raise AssertionError("comparison.py missing")
    spec = importlib.util.spec_from_file_location("comparison", COMPARISON_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class SlotKeysTests(unittest.TestCase):
    def test_new_slot_keys_present(self):
        comp = load_comparison()
        for key in ("sampler", "scheduler", "denoise"):
            self.assertIn(key, comp.SLOT_KEYS)

    def test_old_slot_keys_preserved(self):
        comp = load_comparison()
        for key in ("prompt", "negative_prompt", "seed", "steps",
                    "guidance", "width", "height", "input_image"):
            self.assertIn(key, comp.SLOT_KEYS)


class MappingSummaryTests(unittest.TestCase):
    def test_summary_reports_unmapped_when_empty(self):
        comp = load_comparison()
        profile = {
            "id": "p1",
            "slots": {},
            "loader_target_groups": [],
            "lora_slots": [],
        }
        summary = comp.compute_mapping_summary(profile)
        self.assertFalse(summary["prompt"])
        self.assertFalse(summary["sampler"])
        self.assertFalse(summary["loader_target_groups"])
        self.assertFalse(summary["lora_slots"])

    def test_summary_reports_mapped_when_prompt_mapped(self):
        comp = load_comparison()
        profile = {
            "id": "p1",
            "slots": {
                "prompt": {"node_id": "12", "field": "text", "path": ["inputs", "text"]},
                "sampler": {"node_id": "34", "field": "sampler_name", "path": ["inputs", "sampler_name"]},
            },
            "loader_target_groups": [
                {"id": "g_default", "label": "Default", "unet": [{"node_id": "1", "field": "unet_name"}], "clip": [], "vae": []},
            ],
            "lora_slots": [
                {"slot_index": 0, "lora_node_id": "20", "lora_field": "lora_name",
                 "model_strength_node_id": "20", "model_strength_field": "strength_model",
                 "clip_strength_node_id": "20", "clip_strength_field": "strength_clip"},
            ],
        }
        summary = comp.compute_mapping_summary(profile)
        self.assertTrue(summary["prompt"])
        self.assertTrue(summary["sampler"])
        self.assertTrue(summary["loader_target_groups"])
        self.assertTrue(summary["lora_slots"])


class LoaderTargetGroupTests(unittest.TestCase):
    def test_default_group_constructed_from_existing_mappings(self):
        comp = load_comparison()
        existing = {
            "unet_loader": [{"node_id": "1", "field": "unet_name"}],
            "clip_loader": [{"node_id": "2", "field": "clip_name1"}],
            "vae_loader": [{"node_id": "3", "field": "vae_name"}],
        }
        groups = comp.build_loader_target_groups_from_existing(existing)
        self.assertEqual(len(groups), 1)
        self.assertEqual(groups[0]["id"], "g_default")
        self.assertEqual(groups[0]["label"], "Default")
        self.assertEqual(len(groups[0]["unet"]), 1)

    def test_inject_loader_group_into_workflow(self):
        comp = load_comparison()
        workflow = {
            "1": {"class_type": "UNETLoader",
                  "inputs": {"unet_name": "old_unet.safetensors"}},
            "2": {"class_type": "DualCLIPLoader",
                  "inputs": {"clip_name1": "old_clip.safetensors"}},
            "3": {"class_type": "VAELoader",
                  "inputs": {"vae_name": "old_vae.safetensors"}},
        }
        group = {
            "id": "g_default",
            "unet": [{"node_id": "1", "field": "unet_name"}],
            "clip": [{"node_id": "2", "field": "clip_name1"}],
            "vae": [{"node_id": "3", "field": "vae_name"}],
        }
        triple = {"unet": "new_unet.safetensors",
                  "clip": "new_clip.safetensors",
                  "vae": "new_vae.safetensors"}
        comp.inject_loader_group(workflow, group, triple)
        self.assertEqual(workflow["1"]["inputs"]["unet_name"], "new_unet.safetensors")
        self.assertEqual(workflow["2"]["inputs"]["clip_name1"], "new_clip.safetensors")
        self.assertEqual(workflow["3"]["inputs"]["vae_name"], "new_vae.safetensors")

    def test_inject_loader_group_with_multi_group_fanout(self):
        comp = load_comparison()
        # workflow has TWO UNET loaders and TWO CLIP loaders in one group
        workflow = {
            "1": {"class_type": "UNETLoader", "inputs": {"unet_name": "u1"}},
            "5": {"class_type": "UNETLoader", "inputs": {"unet_name": "u1"}},
            "2": {"class_type": "DualCLIPLoader", "inputs": {"clip_name1": "c1"}},
            "6": {"class_type": "DualCLIPLoader", "inputs": {"clip_name1": "c1"}},
            "3": {"class_type": "VAELoader", "inputs": {"vae_name": "v1"}},
        }
        group = {
            "id": "g_main",
            "unet": [
                {"node_id": "1", "field": "unet_name"},
                {"node_id": "5", "field": "unet_name"},
            ],
            "clip": [
                {"node_id": "2", "field": "clip_name1"},
                {"node_id": "6", "field": "clip_name1"},
            ],
            "vae": [{"node_id": "3", "field": "vae_name"}],
        }
        triple = {"unet": "new.safetensors",
                  "clip": "new_clip.safetensors",
                  "vae": "new_vae.safetensors"}
        comp.inject_loader_group(workflow, group, triple)
        # both UNET loaders updated
        self.assertEqual(workflow["1"]["inputs"]["unet_name"], "new.safetensors")
        self.assertEqual(workflow["5"]["inputs"]["unet_name"], "new.safetensors")
        # both CLIP loaders updated
        self.assertEqual(workflow["2"]["inputs"]["clip_name1"], "new_clip.safetensors")
        self.assertEqual(workflow["6"]["inputs"]["clip_name1"], "new_clip.safetensors")
        self.assertEqual(workflow["3"]["inputs"]["vae_name"], "new_vae.safetensors")


class AlternateTripleTests(unittest.TestCase):
    def test_subprofile_round_trip(self):
        comp = load_comparison()
        profile = {"id": "p1"}
        triple = {"id": "alt_bf16", "label": "BF16",
                  "group_id": "g_default",
                  "unet": "x_bf16.safetensors", "clip": "c.safetensors", "vae": "v.safetensors",
                  "enabled": True}
        comp.add_subprofile(profile, triple)
        self.assertEqual(len(profile["subprofiles"]), 1)
        self.assertEqual(profile["subprofiles"][0]["id"], "alt_bf16")
        # remove
        comp.remove_subprofile(profile, "alt_bf16")
        self.assertEqual(profile["subprofiles"], [])

    def test_subprofile_id_uniqueness_enforced(self):
        comp = load_comparison()
        profile = {"id": "p1", "subprofiles": []}
        comp.add_subprofile(profile, {"id": "a", "label": "A", "group_id": "g", "unet": "", "clip": "", "vae": "", "enabled": True})
        with self.assertRaises(comp.SubprofileError):
            comp.add_subprofile(profile, {"id": "a", "label": "Dup", "group_id": "g", "unet": "", "clip": "", "vae": "", "enabled": True})


class LoRASlotValidationTests(unittest.TestCase):
    def test_lora_selection_within_capacity_is_valid(self):
        comp = load_comparison()
        profile = {
            "id": "p1",
            "lora_slots": [
                {"slot_index": 0, "lora_node_id": "20", "lora_field": "lora_name",
                 "model_strength_node_id": "20", "model_strength_field": "strength_model",
                 "clip_strength_node_id": "20", "clip_strength_field": "strength_clip"},
                {"slot_index": 1, "lora_node_id": "21", "lora_field": "lora_name",
                 "model_strength_node_id": "21", "model_strength_field": "strength_model",
                 "clip_strength_node_id": "21", "clip_strength_field": "strength_clip"},
            ],
        }
        # "No LoRA" selection (zero entries) is valid
        self.assertEqual(comp.validate_lora_selection_against_slots(profile, []), [])
        # selection with 1 LoRA within 2-slot profile is valid
        warnings = comp.validate_lora_selection_against_slots(
            profile, [("a.safetensors", [0.7], [0.7])])
        self.assertEqual(warnings, [])
        # selection with 2 LoRAs matches the 2 slots
        warnings = comp.validate_lora_selection_against_slots(
            profile, [("a.safetensors", [0.7], [0.7]),
                      ("b.safetensors", [0.5], [0.5])])
        self.assertEqual(warnings, [])

    def test_lora_selection_over_capacity_warns(self):
        comp = load_comparison()
        profile = {
            "id": "p1",
            "lora_slots": [
                {"slot_index": 0, "lora_node_id": "20", "lora_field": "lora_name",
                 "model_strength_node_id": "20", "model_strength_field": "strength_model",
                 "clip_strength_node_id": "20", "clip_strength_field": "strength_clip"},
            ],
        }
        warnings = comp.validate_lora_selection_against_slots(
            profile, [("a.safetensors", [0.7], [0.7]),
                      ("b.safetensors", [0.5], [0.5])])
        self.assertTrue(any("exceeds" in w for w in warnings))

    def test_lora_strength_zero_is_kept(self):
        comp = load_comparison()
        profile = {
            "id": "p1",
            "lora_slots": [
                {"slot_index": 0, "lora_node_id": "20", "lora_field": "lora_name",
                 "model_strength_node_id": "20", "model_strength_field": "strength_model",
                 "clip_strength_node_id": "20", "clip_strength_field": "strength_clip"},
            ],
        }
        warnings = comp.validate_lora_selection_against_slots(
            profile, [("a.safetensors", [0.0], [0.0])])
        self.assertEqual(warnings, [])


class MigrationTests(unittest.TestCase):
    def test_v1_profile_migrates_to_v2_with_empty_groups(self):
        comp = load_comparison()
        v1 = {
            "id": "p1",
            "name": "Old",
            "schema_version": 1,
            "slots": {
                "prompt": {"node_id": "12", "field": "text", "path": ["inputs", "text"]},
            },
            "model_stack": {"unet": [], "clip": [], "vae": []},
        }
        v2 = comp.migrate_profile_to_v2(v1)
        self.assertEqual(v2["schema_version"], 2)
        self.assertEqual(v2["loader_target_groups"], [])
        self.assertEqual(v2["lora_slots"], [])
        self.assertEqual(v2["subprofiles"], [])
        # original slot is preserved
        self.assertEqual(v2["slots"]["prompt"]["node_id"], "12")

    def test_v2_profile_unchanged(self):
        comp = load_comparison()
        v2 = {
            "id": "p1",
            "name": "New",
            "schema_version": 2,
            "slots": {},
            "loader_target_groups": [{"id": "g", "label": "G", "unet": [], "clip": [], "vae": []}],
            "lora_slots": [],
            "subprofiles": [],
        }
        out = comp.migrate_profile_to_v2(v2)
        self.assertIs(out, v2)


class NegativePromptInjectionTests(unittest.TestCase):
    """Empty-string negative_prompt must be injected into workflow;
    None must be skipped (workflow keeps its own)."""

    def _make_workflow(self) -> dict:
        return {
            "10": {"class_type": "CLIPTextEncode", "inputs": {"text": "hello"}},
            "12": {"class_type": "CLIPTextEncode", "inputs": {"text": "neg"}},
        }

    def _make_slots(self) -> dict:
        return {
            "prompt": {"node_id": "10", "field": "text", "path": ["inputs", "text"]},
            "negative_prompt": {"node_id": "12", "field": "text", "path": ["inputs", "text"]},
        }

    def test_empty_string_negative_is_injected(self):
        """Empty string negative_prompt MUST clear the workflow field, not be skipped."""
        comp = load_comparison()
        workflow = self._make_workflow()
        slots = self._make_slots()
        shared = {"prompt": "a cat", "negative_prompt": ""}
        result = comp._inject_into_workflow(workflow, slots, shared)
        self.assertEqual(result["12"]["inputs"]["text"], "")

    def test_none_negative_skips_injection(self):
        """None negative_prompt should skip injection so workflow keeps its value."""
        comp = load_comparison()
        workflow = self._make_workflow()
        slots = self._make_slots()
        shared = {"prompt": "a cat"}
        result = comp._inject_into_workflow(workflow, slots, shared)
        self.assertEqual(result["12"]["inputs"]["text"], "neg")

    def test_non_empty_negative_injected(self):
        """Non-empty negative_prompt is injected normally."""
        comp = load_comparison()
        workflow = self._make_workflow()
        slots = self._make_slots()
        shared = {"prompt": "a cat", "negative_prompt": "bad cat"}
        result = comp._inject_into_workflow(workflow, slots, shared)
        self.assertEqual(result["12"]["inputs"]["text"], "bad cat")


class RunComparisonNegativeTests(unittest.TestCase):
    """run_comparison must pass empty negative_prompt through to shared_inputs."""

    def setUp(self):
        self.comp = load_comparison()
        self.tmpdir = tempfile.TemporaryDirectory()
        self.comfyui_root = self.tmpdir.name
        # Create a minimal profile
        wf = {
            "10": {"class_type": "CLIPTextEncode", "inputs": {"text": "hello"}},
            "12": {"class_type": "CLIPTextEncode", "inputs": {"text": "neg"}},
        }
        self.comp.create_profile(
            comfyui_root=self.comfyui_root,
            name="test",
            workflow_api=wf,
            adapter={"slots": {
                "prompt": {"node_id": "10", "field": "text", "path": ["inputs", "text"]},
                "negative_prompt": {"node_id": "12", "field": "text", "path": ["inputs", "text"]},
            }},
        )
        profiles = self.comp.list_profiles(self.comfyui_root)
        self.profile_id = profiles[0]["id"]

    def tearDown(self):
        self.tmpdir.cleanup()

    def test_run_comparison_empty_negative_prompt_injects_empty(self):
        """Empty string negative_prompt in run_comparison should inject empty string."""
        manifest = self.comp.run_comparison(
            comfyui_root=self.comfyui_root,
            prompt_text="a cat",
            seed=42,
            width=512, height=512,
            steps=20, guidance=7.0,
            negative_prompt="",
            input_image=None,
            profile_ids=[self.profile_id],
        )
        resolved = manifest["resolved_profiles"][0]
        self.assertEqual(resolved["status"], "ready")
        # The workflow should have empty negative injected
        wf = resolved["workflow"]
        self.assertEqual(wf["12"]["inputs"]["text"], "")

    def test_run_comparison_none_negative_preserves_workflow(self):
        """None negative_prompt should skip injection, workflow keeps its negative."""
        manifest = self.comp.run_comparison(
            comfyui_root=self.comfyui_root,
            prompt_text="a cat",
            seed=42,
            width=512, height=512,
            steps=20, guidance=7.0,
            negative_prompt=None,
            input_image=None,
            profile_ids=[self.profile_id],
        )
        resolved = manifest["resolved_profiles"][0]
        self.assertEqual(resolved["status"], "ready")
        wf = resolved["workflow"]
        self.assertEqual(wf["12"]["inputs"]["text"], "neg")


class ProfileAssociationTests(unittest.TestCase):
    """Fail hard on missing profile workflow association."""

    def test_missing_profile_returns_error(self):
        comp = load_comparison()
        with tempfile.TemporaryDirectory() as tmp:
            manifest = comp.run_comparison(
                comfyui_root=tmp,
                prompt_text="a cat",
                seed=42,
                width=512, height=512,
                steps=20, guidance=7.0,
                negative_prompt=None,
                input_image=None,
                profile_ids=["nonexistent"],
            )
            resolved = manifest["resolved_profiles"][0]
            self.assertEqual(resolved["status"], "error")
            self.assertIn("not found", resolved.get("error", "").lower())

    def test_missing_workflow_api_returns_error(self):
        comp = load_comparison()
        with tempfile.TemporaryDirectory() as tmp:
            profiles_root = comp._profiles_root(tmp)
            pid = comp._make_profile_id("orphan")
            profile_dir = os.path.join(profiles_root, pid)
            os.makedirs(profile_dir, exist_ok=True)
            # Write only profile.json, no workflow_api.json
            import json
            with open(os.path.join(profile_dir, "profile.json"), "w") as f:
                json.dump({"id": pid, "name": "Orphan", "slots": {}}, f)
            manifest = comp.run_comparison(
                comfyui_root=tmp,
                prompt_text="a cat",
                seed=42,
                width=512, height=512,
                steps=20, guidance=7.0,
                negative_prompt=None,
                input_image=None,
                profile_ids=[pid],
            )
            resolved = manifest["resolved_profiles"][0]
            self.assertEqual(resolved["status"], "error")
            self.assertIn("workflow", resolved.get("error", "").lower())

    def test_missing_prompt_slot_returns_error(self):
        comp = load_comparison()
        with tempfile.TemporaryDirectory() as tmp:
            wf = {"10": {"class_type": "CLIPTextEncode", "inputs": {"text": "hello"}}}
            comp.create_profile(
                comfyui_root=tmp,
                name="no_prompt_slot",
                workflow_api=wf,
                adapter={"slots": {}},  # no prompt slot
            )
            profiles = comp.list_profiles(tmp)
            pid = profiles[0]["id"]
            manifest = comp.run_comparison(
                comfyui_root=tmp,
                prompt_text="a cat",
                seed=42,
                width=512, height=512,
                steps=20, guidance=7.0,
                negative_prompt=None,
                input_image=None,
                profile_ids=[pid],
            )
            resolved = manifest["resolved_profiles"][0]
            self.assertEqual(resolved["status"], "error")
            self.assertIn("prompt slot", resolved.get("error", "").lower())


class UpdateProfileWorkflowTests(unittest.TestCase):
    """update_profile must accept workflow_api and/or workflow and
    rewrite the on-disk files plus recalc metadata."""

    def setUp(self):
        self.comp = load_comparison()
        self.tmpdir = tempfile.TemporaryDirectory()
        self.root = self.tmpdir.name
        self.wf_orig = {
            "10": {"class_type": "CLIPTextEncode", "inputs": {"text": "hello"}},
            "6": {"class_type": "KSampler", "inputs": {"seed": 42, "steps": 20, "cfg": 7.0}},
        }
        self.profile = self.comp.create_profile(
            comfyui_root=self.root,
            name="test_update_wf",
            workflow_api=self.wf_orig,
            adapter={"slots": {
                "prompt": {"node_id": "10", "field": "text", "path": ["inputs", "text"]},
            }},
        )
        self.pid = self.profile["id"]

    def tearDown(self):
        self.tmpdir.cleanup()

    def test_update_profile_accepts_new_workflow_api(self):
        """update_profile with workflow_api rewrites on-disk file and recalculates hash."""
        new_wf = {
            "10": {"class_type": "CLIPTextEncode", "inputs": {"text": "updated prompt"}},
            "6": {"class_type": "KSampler", "inputs": {"seed": 99, "steps": 30, "cfg": 8.0}},
        }
        updated = self.comp.update_profile(self.root, self.pid, {"workflow_api": new_wf})
        self.assertIsNotNone(updated)
        # Verify recalculated hash differs from original
        orig_hash = self.profile["workflow_hash"]
        self.assertNotEqual(updated["workflow_hash"], orig_hash)
        self.assertEqual(updated["workflow_hash"], self.comp._workflow_sha256(new_wf))
        # Verify on-disk file was rewritten
        profiles_root = self.comp._profiles_root(self.root)
        on_disk = self.comp._load_workflow_api(profiles_root, self.pid)
        self.assertEqual(on_disk, new_wf)

    def test_update_profile_accepts_workflow_ui(self):
        """update_profile with workflow rewrites workflow.json on disk."""
        new_ui = {"nodes": [{"id": 10, "type": "CLIPTextEncode", "title": "New Title"}]}
        updated = self.comp.update_profile(self.root, self.pid, {"workflow": new_ui})
        self.assertIsNotNone(updated)
        # Verify on-disk UI workflow was written
        profiles_root = self.comp._profiles_root(self.root)
        ui_path = self.comp._workflow_ui_path(profiles_root, self.pid)
        self.assertTrue(os.path.isfile(ui_path))
        with open(ui_path, "r") as f:
            self.assertEqual(json.load(f), new_ui)

    def test_update_profile_workflow_api_recomputes_capabilities(self):
        """Adding an input_image slot via new workflow_api should update capabilities."""
        new_wf = {
            "10": {"class_type": "CLIPTextEncode", "inputs": {"text": "hello"}},
            "5": {"class_type": "LoadImage", "inputs": {"image": "photo.png"}},
        }
        updated = self.comp.update_profile(self.root, self.pid, {"workflow_api": new_wf})
        self.assertIsNotNone(updated)
        # capabilities should reflect the new workflow even though
        # slots haven't been updated yet (no input_image mapping yet)
        # capabilities are workflow-derived, so this should still compute correctly
        self.assertIn("capabilities", updated)

    def test_update_profile_with_both_workflow_and_workflow_api(self):
        """update_profile can accept both workflow API and UI formats simultaneously."""
        new_wf = {"1": {"class_type": "KSampler", "inputs": {"seed": 1}}}
        new_ui = {"nodes": [{"id": 1, "type": "KSampler", "title": "S"}]}
        updated = self.comp.update_profile(self.root, self.pid, {
            "workflow_api": new_wf,
            "workflow": new_ui,
        })
        self.assertIsNotNone(updated)
        profiles_root = self.comp._profiles_root(self.root)
        # Both files should exist on disk
        api_disk = self.comp._load_workflow_api(profiles_root, self.pid)
        self.assertEqual(api_disk, new_wf)
        profiles_root = self.comp._profiles_root(self.root)
        ui_disk = self.comp._load_workflow_ui(profiles_root, self.pid)
        self.assertEqual(ui_disk, new_ui)


# ── D3: Profile workflow contract ────────────────────────────────────────

class ProfileWorkflowContractTests(unittest.TestCase):
    """D3: Profile behavior must be explicit and isolated."""

    def setUp(self):
        self.comp = load_comparison()
        self.tmpdir = tempfile.TemporaryDirectory()
        self.root = self.tmpdir.name
        self.wf_a = {
            "10": {"class_type": "CLIPTextEncode", "inputs": {"text": "hello"}},
            "6": {"class_type": "KSampler", "inputs": {"seed": 42, "steps": 20, "cfg": 7.0}},
        }
        self.wf_b = {
            "10": {"class_type": "CLIPTextEncode", "inputs": {"text": "world"}},
            "6": {"class_type": "KSampler", "inputs": {"seed": 99, "steps": 30, "cfg": 8.0}},
        }
        self.profile_a = self.comp.create_profile(
            comfyui_root=self.root, name="Profile A",
            workflow_api=self.wf_a,
            adapter={"slots": {"prompt": {"node_id": "10", "field": "text", "path": ["inputs", "text"]}}},
        )
        self.pid_a = self.profile_a["id"]
        self.profile_b = self.comp.create_profile(
            comfyui_root=self.root, name="Profile B",
            workflow_api=self.wf_b,
            adapter={"slots": {"prompt": {"node_id": "10", "field": "text", "path": ["inputs", "text"]}}},
        )
        self.pid_b = self.profile_b["id"]

    def tearDown(self):
        self.tmpdir.cleanup()

    def test_update_profile_writes_on_disk_file(self):
        """update_profile must write the workflow_api.json to disk."""
        new_wf = {"1": {"class_type": "KSampler", "inputs": {"seed": 1}}}
        self.comp.update_profile(self.root, self.pid_a, {"workflow_api": new_wf})
        profiles_root = self.comp._profiles_root(self.root)
        on_disk = self.comp._load_workflow_api(profiles_root, self.pid_a)
        self.assertEqual(on_disk, new_wf)

    def test_update_profile_recomputes_hash(self):
        """update_profile must recompute workflow_hash."""
        orig_hash = self.profile_a["workflow_hash"]
        new_wf = {"1": {"class_type": "KSampler", "inputs": {"seed": 1}}}
        updated = self.comp.update_profile(self.root, self.pid_a, {"workflow_api": new_wf})
        self.assertIsNotNone(updated)
        self.assertNotEqual(updated["workflow_hash"], orig_hash)
        self.assertEqual(updated["workflow_hash"], self.comp._workflow_sha256(new_wf))

    def test_update_profile_recomputes_model_stack(self):
        """update_profile must recompute model_stack from workflow_api."""
        updated = self.comp.update_profile(self.root, self.pid_a, {"workflow_api": self.wf_a})
        self.assertIsNotNone(updated)
        self.assertIn("model_stack", updated)

    def test_update_profile_recomputes_capabilities(self):
        """update_profile must recompute capabilities from workflow_api and slots."""
        updated = self.comp.update_profile(self.root, self.pid_a, {"workflow_api": self.wf_a})
        self.assertIsNotNone(updated)
        caps = updated.get("capabilities", {})
        self.assertIn("txt2img", caps)
        self.assertIn("img2img", caps)

    def test_profile_a_isolated_from_profile_b(self):
        """Updating profile A must not affect profile B."""
        new_wf_a = {"1": {"class_type": "KSampler", "inputs": {"seed": 777}}}
        self.comp.update_profile(self.root, self.pid_a, {"workflow_api": new_wf_a})
        profiles_root = self.comp._profiles_root(self.root)
        wf_a_disk = self.comp._load_workflow_api(profiles_root, self.pid_a)
        wf_b_disk = self.comp._load_workflow_api(profiles_root, self.pid_b)
        self.assertEqual(wf_a_disk, new_wf_a)
        self.assertEqual(wf_b_disk, self.wf_b)  # profile B unchanged

    def test_missing_profile_workflow_fails_clearly(self):
        """Missing workflow_api.json must be reported clearly."""
        profiles_root = self.comp._profiles_root(self.root)
        # Create an orphan profile dir with no workflow_api.json
        orphan_id = self.comp._make_profile_id("orphan")
        os.makedirs(os.path.join(profiles_root, orphan_id), exist_ok=True)
        import json
        with open(os.path.join(profiles_root, orphan_id, "profile.json"), "w") as f:
            json.dump({"id": orphan_id, "name": "Orphan", "slots": {}}, f)
        validation = self.comp.validate_profile(self.root, orphan_id)
        self.assertEqual(validation["status"], "invalid")
        self.assertTrue(any("workflow" in e.lower() for e in validation.get("errors", [])))


if __name__ == "__main__":
    unittest.main()
