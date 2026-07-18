"""Focused tests for restore_plan: DualCLIPLoader identity, safe generation, reload authority."""

from __future__ import annotations

import tempfile
import unittest

from comfymodal_runtime.contracts import (
    ModelRestoreKey,
    PrefillKey,
    RestorePlan,
)
from comfymodal_runtime.restore_plan import (
    _build_dual_clip_identity,
    _extract_model_references,
    _extract_prompt_texts,
    derive_model_key,
    derive_prefill_key,
    RestorePlanPublisher,
)
from comfymodal_runtime.runtime_state import (
    CommitCoordinator,
    FakeVolume,
    MountedStateVolume,
)


# ---------------------------------------------------------------------------
# _build_dual_clip_identity
# ---------------------------------------------------------------------------

class TestBuildDualClipIdentity(unittest.TestCase):
    def test_identical_names_returns_single(self):
        identity = _build_dual_clip_identity("clip_l.safetensors", "clip_l.safetensors")
        self.assertEqual(identity, "clip_l.safetensors")

    def test_different_names_concatenated(self):
        identity = _build_dual_clip_identity("clip_l.safetensors", "clip_g.safetensors")
        self.assertEqual(identity, "clip_l.safetensors||clip_g.safetensors")

    def test_empty_names(self):
        identity = _build_dual_clip_identity("", "clip_g.safetensors")
        self.assertEqual(identity, "||clip_g.safetensors")

    def test_both_empty(self):
        identity = _build_dual_clip_identity("", "")
        self.assertEqual(identity, "")


# ---------------------------------------------------------------------------
# _extract_model_references — DualCLIPLoader
# ---------------------------------------------------------------------------

class TestExtractModelReferencesDualCLIP(unittest.TestCase):
    def test_dual_clip_concatenates_both_names(self):
        workflow = {
            "10": {
                "class_type": "DualCLIPLoader",
                "inputs": {
                    "clip_name1": "clip_l.safetensors",
                    "clip_name2": "clip_g.safetensors",
                    "type": "flux",
                },
            },
        }
        refs = _extract_model_references(workflow)
        self.assertEqual(refs["clip"], "clip_l.safetensors||clip_g.safetensors")
        self.assertEqual(refs["clip_type"], "flux")

    def test_dual_clip_identical_names(self):
        workflow = {
            "10": {
                "class_type": "DualCLIPLoader",
                "inputs": {
                    "clip_name1": "model.safetensors",
                    "clip_name2": "model.safetensors",
                },
            },
        }
        refs = _extract_model_references(workflow)
        self.assertEqual(refs["clip"], "model.safetensors")

    def test_dual_clip_changing_one_name_changes_identity(self):
        """Swapping clip_name2 must produce a different clip identity."""
        workflow_a = {
            "10": {
                "class_type": "DualCLIPLoader",
                "inputs": {"clip_name1": "l.safetensors", "clip_name2": "g.safetensors"},
            },
        }
        workflow_b = {
            "10": {
                "class_type": "DualCLIPLoader",
                "inputs": {"clip_name1": "l.safetensors", "clip_name2": "g2.safetensors"},
            },
        }
        refs_a = _extract_model_references(workflow_a)
        refs_b = _extract_model_references(workflow_b)
        self.assertNotEqual(refs_a["clip"], refs_b["clip"])

    def test_dual_clip_only_clip_name1(self):
        workflow = {
            "10": {
                "class_type": "DualCLIPLoader",
                "inputs": {"clip_name1": "only_l.safetensors"},
            },
        }
        refs = _extract_model_references(workflow)
        self.assertEqual(refs["clip"], "only_l.safetensors||")

    def test_dual_clip_does_not_affect_unet_vae(self):
        workflow = {
            "10": {
                "class_type": "DualCLIPLoader",
                "inputs": {"clip_name1": "l.sft", "clip_name2": "g.sft"},
            },
        }
        refs = _extract_model_references(workflow)
        self.assertNotIn("unet", refs)
        self.assertNotIn("vae", refs)
        self.assertIn("clip", refs)


# ---------------------------------------------------------------------------
# derive_model_key — DualCLIPLoader contributes to identity
# ---------------------------------------------------------------------------

class TestDeriveModelKeyDualCLIP(unittest.TestCase):
    def test_dual_clip_changes_model_key_hash(self):
        workflow_a = {
            "10": {
                "class_type": "DualCLIPLoader",
                "inputs": {"clip_name1": "l.sft", "clip_name2": "g.sft"},
            },
        }
        workflow_b = {
            "10": {
                "class_type": "DualCLIPLoader",
                "inputs": {"clip_name1": "l.sft", "clip_name2": "g2.sft"},
            },
        }
        key_a = derive_model_key(workflow_a)
        key_b = derive_model_key(workflow_b)
        self.assertNotEqual(key_a.stable_hash, key_b.stable_hash,
                            "Changing clip_name2 must change model key hash")

    def test_dual_clip_identical_names_same_hash(self):
        workflow_a = {
            "10": {
                "class_type": "DualCLIPLoader",
                "inputs": {"clip_name1": "same.sft", "clip_name2": "same.sft"},
            },
        }
        workflow_b = {
            "10": {
                "class_type": "DualCLIPLoader",
                "inputs": {"clip_name1": "same.sft", "clip_name2": "same.sft"},
            },
        }
        key_a = derive_model_key(workflow_a)
        key_b = derive_model_key(workflow_b)
        self.assertEqual(key_a.stable_hash, key_b.stable_hash)


# ---------------------------------------------------------------------------
# _safe_generation
# ---------------------------------------------------------------------------

class TestSafeGeneration(unittest.TestCase):
    def test_int_preserved(self):
        self.assertEqual(RestorePlanPublisher._safe_generation(42), 42)

    def test_numeric_string(self):
        self.assertEqual(RestorePlanPublisher._safe_generation("42"), 42)

    def test_non_numeric_string_returns_zero(self):
        self.assertEqual(RestorePlanPublisher._safe_generation("abc"), 0)

    def test_empty_string_returns_zero(self):
        self.assertEqual(RestorePlanPublisher._safe_generation(""), 0)

    def test_zero_returns_zero(self):
        self.assertEqual(RestorePlanPublisher._safe_generation(0), 0)

    def test_negative_int_preserved(self):
        self.assertEqual(RestorePlanPublisher._safe_generation(-1), -1)


# ---------------------------------------------------------------------------
# RestorePlanPublisher — reload authority, commit behavior
# ---------------------------------------------------------------------------

class TestRestorePlanPublisher(unittest.TestCase):
    def test_publish_new_plan_with_fake_volume(self):
        volume = FakeVolume()
        coord = CommitCoordinator(volume, state_path="restore.json")
        publisher = RestorePlanPublisher(coord)
        plan = RestorePlan(generation=1, source_workflow_hash="wf1")
        gen = publisher.publish(plan)
        self.assertEqual(gen, 1)
        self.assertEqual(coord.committed_generation, 1)

    def test_publish_noop_when_unchanged(self):
        volume = FakeVolume()
        coord = CommitCoordinator(volume, state_path="restore.json")
        publisher = RestorePlanPublisher(coord)
        plan = RestorePlan(generation=1, source_workflow_hash="wf1")
        gen1 = publisher.publish(plan)
        gen2 = publisher.publish(plan)  # same plan, no write expected
        self.assertEqual(gen1, 1)
        self.assertEqual(gen2, 1)
        m = coord.metrics
        self.assertEqual(m.write_count, 1,
                         "No additional write for unchanged plan")
        self.assertEqual(m.commit_count, 1,
                         "No additional commit for unchanged plan")

    def test_publish_changed_plan_writes_and_commits(self):
        volume = FakeVolume()
        coord = CommitCoordinator(volume, state_path="restore.json")
        publisher = RestorePlanPublisher(coord)
        plan1 = RestorePlan(generation=1, source_workflow_hash="wf1")
        plan2 = RestorePlan(generation=2, source_workflow_hash="wf2")
        publisher.publish(plan1)
        publisher.publish(plan2)
        m = coord.metrics
        self.assertEqual(m.write_count, 2)
        self.assertEqual(m.commit_count, 2)

    def test_publish_with_mounted_volume(self):
        """Full publish cycle with real filesystem."""
        with tempfile.TemporaryDirectory() as tmp:
            volume = MountedStateVolume(root=tmp)
            coord = CommitCoordinator(volume, state_path="plan.json")
            publisher = RestorePlanPublisher(coord)
            plan = RestorePlan(generation=3, source_workflow_hash="wf3")
            gen = publisher.publish(plan)
            self.assertEqual(gen, 3)
            self.assertEqual(coord.committed_generation, 3)
            self.assertEqual(volume.commit_count, 1)

    def test_publish_reloads_authoritative_state(self):
        """publish must reload from volume — simulate external write."""
        volume = FakeVolume()
        coord = CommitCoordinator(volume, state_path="restore.json")
        publisher = RestorePlanPublisher(coord)
        plan = RestorePlan(generation=1, source_workflow_hash="wf1")
        publisher.publish(plan)

        # Simulate external write to the volume at a higher generation
        external = RestorePlan(generation=5, source_workflow_hash="wf_ext")
        coord.write_state(5, {"restore_plan": external.to_dict()})
        coord.commit(5)

        # Publish an identical plan — should detect it's already current
        # by reloading from volume and return gen 5, not re-write.
        same_as_external = RestorePlan(generation=5, source_workflow_hash="wf_ext")
        gen = publisher.publish(same_as_external)
        self.assertEqual(gen, 5)
        m = coord.metrics
        # The external write added 1 write + 1 commit; the no-op publish
        # should not add more.
        self.assertEqual(m.write_count, 2,
                         "No write for already-published plan")
        self.assertEqual(m.commit_count, 2,
                         "No commit for already-published plan")

    def test_non_numeric_generation_safe(self):
        """Non-numeric generation in plan is safely coerced."""
        volume = FakeVolume()
        coord = CommitCoordinator(volume)
        publisher = RestorePlanPublisher(coord)
        plan = RestorePlan(generation="abc", source_workflow_hash="wf")
        gen = publisher.publish(plan)
        self.assertEqual(gen, 0,
                         "Non-numeric generation should coerce to 0")


# ---------------------------------------------------------------------------
# Legacy tests (migrated from test_runtime_contracts)
# ---------------------------------------------------------------------------

class TestDeriveModelKey(unittest.TestCase):
    def test_checkpoint_loader(self):
        workflow = {
            "3": {
                "class_type": "CheckpointLoaderSimple",
                "inputs": {"ckpt_name": "model.safetensors"},
            },
        }
        key = derive_model_key(workflow)
        self.assertEqual(key.unet_identity, "model.safetensors")
        self.assertEqual(key.clip_identity, "model.safetensors")
        self.assertEqual(key.vae_identity, "model.safetensors")

    def test_split_loaders(self):
        workflow = {
            "3": {
                "class_type": "UNETLoader",
                "inputs": {"unet_name": "unet.safetensors"},
            },
            "4": {
                "class_type": "CLIPLoader",
                "inputs": {"clip_name": "clip.safetensors", "type": "flux"},
            },
            "5": {
                "class_type": "VAELoader",
                "inputs": {"vae_name": "vae.safetensors"},
            },
        }
        key = derive_model_key(workflow)
        self.assertEqual(key.unet_identity, "unet.safetensors")
        self.assertEqual(key.clip_identity, "clip.safetensors")
        self.assertEqual(key.vae_identity, "vae.safetensors")
        self.assertEqual(key.clip_type, "flux")


class TestDerivePrefillKey(unittest.TestCase):
    def test_prompt_text_changes_prefill_not_model(self):
        model_key = ModelRestoreKey(unet_identity="u", clip_identity="c")
        wf_a = {"6": {"class_type": "CLIPTextEncode", "inputs": {"text": "a dog"}}}
        wf_b = {"6": {"class_type": "CLIPTextEncode", "inputs": {"text": "a cat"}}}
        pa = derive_prefill_key(model_key, wf_a)
        pb = derive_prefill_key(model_key, wf_b)
        self.assertEqual(pa.model_key.stable_hash, pb.model_key.stable_hash)
        self.assertNotEqual(pa.stable_hash, pb.stable_hash)


if __name__ == "__main__":
    unittest.main()
