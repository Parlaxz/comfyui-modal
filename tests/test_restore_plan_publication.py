"""Focused tests for restore_plan: key derivation, unchanged/prompt/model changes."""

from __future__ import annotations

import unittest

from comfymodal_runtime.contracts import (
    ModelRestoreKey,
    PrefillKey,
    RestorePlan,
    stable_hash,
)
from comfymodal_runtime.restore_plan import (
    RestorePlanPublisher,
    derive_model_key,
    derive_prefill_key,
)
from comfymodal_runtime.runtime_state import CommitCoordinator, FakeVolume


# ── Workflow fixtures ────────────────────────────────────────────────────


def _workflow_with_models(
    unet: str = "flux1.safetensors",
    clip: str = "clip_l.safetensors",
    vae: str = "vae.safetensors",
    clip_type: str = "flux",
    **extra_inputs: str,
) -> dict:
    """Build a minimal workflow dict with model loaders."""
    nodes: dict = {
        "1": {
            "class_type": "UNETLoader",
            "inputs": {"unet_name": unet},
        },
        "2": {
            "class_type": "CLIPLoader",
            "inputs": {"clip_name": clip, "type": clip_type},
        },
        "3": {
            "class_type": "VAELoader",
            "inputs": {"vae_name": vae},
        },
        "4": {
            "class_type": "CLIPTextEncode",
            "inputs": {"text": extra_inputs.get("prompt", "a cat"),
                       "clip": ["2", 0]},
        },
    }
    return nodes


def _workflow_with_prompt(prompt: str = "a cat") -> dict:
    """Build a minimal workflow with a safely resolvable CLIP loader."""
    return {
        "2": {
            "class_type": "CLIPLoader",
            "inputs": {"clip_name": "clip_l.safetensors", "type": "flux"},
        },
        "4": {
            "class_type": "CLIPTextEncode",
            "inputs": {"text": prompt, "clip": ["2", 0]},
        },
    }


# ── Tests: derive_model_key ──────────────────────────────────────────────


class TestDeriveModelKey(unittest.TestCase):
    """Model key includes only loader identities; excludes prompt/seed/output."""

    def test_extracts_unet_clip_vae(self):
        wf = _workflow_with_models()
        key = derive_model_key(wf)
        self.assertEqual(key.unet_identity, "flux1.safetensors")
        self.assertEqual(key.clip_identity, "clip_l.safetensors")
        self.assertEqual(key.vae_identity, "vae.safetensors")

    def test_extracts_clip_type(self):
        wf = _workflow_with_models(clip_type="sd3")
        key = derive_model_key(wf)
        self.assertEqual(key.clip_type, "sd3")

    def test_changing_prompt_does_not_affect_model_key(self):
        wf1 = _workflow_with_models(prompt="a cat")
        wf2 = _workflow_with_models(prompt="a dog")
        key1 = derive_model_key(wf1)
        key2 = derive_model_key(wf2)
        self.assertEqual(key1.stable_hash, key2.stable_hash,
                         "Changing prompt should NOT change model key")

    def test_changing_seed_does_not_affect_model_key(self):
        wf1 = _workflow_with_models()
        wf2 = _workflow_with_models()
        # Add a KSampler node with different seed
        wf2["5"] = {
            "class_type": "KSampler",
            "inputs": {"seed": 42, "steps": 20},
        }
        key1 = derive_model_key(wf1)
        key2 = derive_model_key(wf2)
        self.assertEqual(key1.stable_hash, key2.stable_hash,
                         "Changing seed should NOT change model key")

    def test_changing_model_alters_model_key(self):
        wf1 = _workflow_with_models(unet="model_a.safetensors")
        wf2 = _workflow_with_models(unet="model_b.safetensors")
        self.assertNotEqual(
            derive_model_key(wf1).stable_hash,
            derive_model_key(wf2).stable_hash,
        )

    def test_changing_clip_alters_model_key(self):
        wf1 = _workflow_with_models(clip="clip_a.safetensors")
        wf2 = _workflow_with_models(clip="clip_b.safetensors")
        self.assertNotEqual(
            derive_model_key(wf1).stable_hash,
            derive_model_key(wf2).stable_hash,
        )

    def test_checkpoint_loader_extracts_all_three(self):
        wf = {
            "1": {
                "class_type": "CheckpointLoaderSimple",
                "inputs": {"ckpt_name": "sd_xl.safetensors"},
            },
        }
        key = derive_model_key(wf)
        self.assertEqual(key.unet_identity, "sd_xl.safetensors")
        self.assertEqual(key.clip_identity, "sd_xl.safetensors")
        self.assertEqual(key.vae_identity, "sd_xl.safetensors")

    def test_empty_workflow_yields_empty_key(self):
        key = derive_model_key({})
        self.assertEqual(key.unet_identity, "")
        self.assertEqual(key.clip_identity, "")
        self.assertEqual(key.vae_identity, "")


# ── Tests: derive_prefill_key ────────────────────────────────────────────


class TestDerivePrefillKey(unittest.TestCase):
    """Prefill key includes model identity + prompt bundle hash."""

    def test_model_key_is_preserved(self):
        model_key = ModelRestoreKey(unet_identity="u", clip_identity="c")
        wf = _workflow_with_prompt("hello")
        prefill = derive_prefill_key(model_key, wf)
        self.assertEqual(prefill.model_key.stable_hash, model_key.stable_hash)

    def test_prompt_change_alters_prefill_but_not_model(self):
        model_key = ModelRestoreKey(unet_identity="u")
        wf1 = _workflow_with_prompt("hello")
        wf2 = _workflow_with_prompt("world")

        prefill1 = derive_prefill_key(model_key, wf1)
        prefill2 = derive_prefill_key(model_key, wf2)

        # Model hash unchanged
        self.assertEqual(
            prefill1.model_key.stable_hash,
            prefill2.model_key.stable_hash,
        )
        # Prefill hash changed
        self.assertNotEqual(prefill1.stable_hash, prefill2.stable_hash)

    def test_multiple_prompts_are_sorted_deterministically(self):
        model_key = ModelRestoreKey(unet_identity="u")
        wf = {
            "2": {
                "class_type": "CLIPLoader",
                "inputs": {"clip_name": "clip_l.safetensors", "type": "flux"},
            },
            "4": {"class_type": "CLIPTextEncode", "inputs": {"text": "B", "clip": ["2", 0]}},
            "5": {"class_type": "CLIPTextEncode", "inputs": {"text": "A", "clip": ["2", 0]}},
        }
        prefill = derive_prefill_key(model_key, wf)
        self.assertNotEqual(prefill.prompt_bundle_hash, "")

    def test_no_prompt_nodes_yields_empty_bundle_hash(self):
        model_key = ModelRestoreKey(unet_identity="u")
        prefill = derive_prefill_key(model_key, {})
        self.assertEqual(prefill.prompt_bundle_hash, "")

    def test_unsupported_sdxl_encode_is_not_prefill_eligible(self):
        model_key = ModelRestoreKey(unet_identity="u")
        wf = {
            "4": {
                "class_type": "CLIPTextEncodeSDXL",
                "inputs": {"text": "sdxl prompt", "clip": ["2", 0]},
            },
        }
        prefill = derive_prefill_key(model_key, wf)
        self.assertEqual(prefill.prompt_bundle_hash, "")
        self.assertFalse(prefill.encode_options["eligible"])

    def test_stable_hash_differs_for_different_prompts(self):
        """Two PrefillKeys with different prompts but same model have different hashes."""
        model_key = ModelRestoreKey(unet_identity="u")
        p1 = derive_prefill_key(model_key, _workflow_with_prompt("cat"))
        p2 = derive_prefill_key(model_key, _workflow_with_prompt("dog"))
        self.assertNotEqual(p1.stable_hash, p2.stable_hash)


# ── Tests: RestorePlanPublisher ──────────────────────────────────────────


class TestRestorePlanPublisher(unittest.TestCase):
    """Publisher behavior: no-op when unchanged, writes when changed."""

    def setUp(self):
        self.volume = FakeVolume()
        self.coord = CommitCoordinator(self.volume)
        self.publisher = RestorePlanPublisher(self.coord)

    def test_first_publish_writes_and_commits(self):
        plan = RestorePlan(
            generation=1,
            model_key=ModelRestoreKey(unet_identity="u"),
            prefill_key=PrefillKey(prompt_bundle_hash="p1"),
        )
        gen = self.publisher.publish(plan)
        self.assertEqual(gen, 1)
        self.assertEqual(self.coord.committed_generation, 1)
        self.assertEqual(self.coord.metrics.write_count, 1)
        self.assertEqual(self.coord.metrics.commit_count, 1)

    def test_identical_plan_does_not_write(self):
        plan = RestorePlan(
            generation=1,
            model_key=ModelRestoreKey(unet_identity="u"),
            prefill_key=PrefillKey(prompt_bundle_hash="p1"),
        )
        self.publisher.publish(plan)
        write_count_after_first = self.coord.metrics.write_count

        # Publish the same plan again
        gen = self.publisher.publish(plan)
        self.assertEqual(gen, 1)
        # No additional writes or commits
        self.assertEqual(self.coord.metrics.write_count, write_count_after_first)
        self.assertEqual(self.coord.metrics.commit_count, 1)

    def test_changed_plan_writes_and_commits(self):
        plan1 = RestorePlan(
            generation=1,
            model_key=ModelRestoreKey(unet_identity="u1"),
            prefill_key=PrefillKey(prompt_bundle_hash="p1"),
        )
        plan2 = RestorePlan(
            generation=2,
            model_key=ModelRestoreKey(unet_identity="u2"),
            prefill_key=PrefillKey(prompt_bundle_hash="p2"),
        )

        self.publisher.publish(plan1)
        write_count = self.coord.metrics.write_count

        gen = self.publisher.publish(plan2)
        self.assertEqual(gen, 2)
        # New write + commit happened
        self.assertGreater(self.coord.metrics.write_count, write_count)
        self.assertEqual(self.coord.metrics.commit_count, 2)

    def test_prompt_only_change_does_not_alter_model_identity(self):
        """Changing only prompt text changes prefill but not model key in published plan."""
        model_key = ModelRestoreKey(unet_identity="u1")
        plan1 = RestorePlan(
            generation=1,
            model_key=model_key,
            prefill_key=PrefillKey(
                model_key=model_key, prompt_bundle_hash="prompt-v1"
            ),
        )
        plan2 = RestorePlan(
            generation=2,
            model_key=model_key,
            prefill_key=PrefillKey(
                model_key=model_key, prompt_bundle_hash="prompt-v2"
            ),
        )

        gen1 = self.publisher.publish(plan1)
        gen2 = self.publisher.publish(plan2)

        # Prefill hashes differ
        self.assertNotEqual(plan1.prefill_key.stable_hash, plan2.prefill_key.stable_hash)
        # Model hashes are the same
        self.assertEqual(
            plan1.model_key.stable_hash, plan2.model_key.stable_hash
        )
        # Generation advanced
        self.assertEqual(gen2, 2)

    def test_model_change_writes_new_plan(self):
        plan1 = RestorePlan(
            generation=1,
            model_key=ModelRestoreKey(unet_identity="old"),
            prefill_key=PrefillKey(prompt_bundle_hash="p"),
        )
        plan2 = RestorePlan(
            generation=2,
            model_key=ModelRestoreKey(unet_identity="new"),
            prefill_key=PrefillKey(prompt_bundle_hash="p"),
        )

        self.publisher.publish(plan1)
        write_before = self.coord.metrics.write_count

        self.publisher.publish(plan2)
        self.assertGreater(self.coord.metrics.write_count, write_before,
                           "Model change should write a new plan")

    def test_commits_exactly_once_per_publish(self):
        """Each unique publish triggers exactly one commit."""
        plan1 = RestorePlan(
            generation=1,
            model_key=ModelRestoreKey(unet_identity="u"),
            prefill_key=PrefillKey(prompt_bundle_hash="p1"),
        )
        plan2 = RestorePlan(
            generation=2,
            model_key=ModelRestoreKey(unet_identity="u2"),
            prefill_key=PrefillKey(prompt_bundle_hash="p2"),
        )

        self.publisher.publish(plan1)
        self.assertEqual(self.coord.metrics.commit_count, 1)

        self.publisher.publish(plan2)
        self.assertEqual(self.coord.metrics.commit_count, 2)


# ── Tests: monotonic generation (default-gen-0 advances) ──────────────


class TestMonotonicGeneration(unittest.TestCase):
    """When the incoming generation is the default (0) or behind the
    authoritative state, a changed plan must advance."""

    def setUp(self):
        self.volume = FakeVolume()
        self.coord = CommitCoordinator(self.volume)
        self.publisher = RestorePlanPublisher(self.coord)

    def test_first_publish_of_gen_zero_remains_zero(self):
        """The first publish with generation=0 stays 0."""
        plan = RestorePlan(
            generation=0,
            model_key=ModelRestoreKey(unet_identity="u"),
            prefill_key=PrefillKey(prompt_bundle_hash="p1"),
        )
        gen = self.publisher.publish(plan)
        self.assertEqual(gen, 0)
        self.assertEqual(self.coord.committed_generation, 0)

    def test_changed_plan_with_gen_zero_advances_to_one(self):
        """A changed plan after generation 0 advances to generation 1."""
        plan1 = RestorePlan(
            generation=0,
            model_key=ModelRestoreKey(unet_identity="u"),
            prefill_key=PrefillKey(prompt_bundle_hash="p1"),
        )
        plan2 = RestorePlan(
            generation=0,
            model_key=ModelRestoreKey(unet_identity="u2"),
            prefill_key=PrefillKey(prompt_bundle_hash="p2"),
        )
        gen1 = self.publisher.publish(plan1)
        self.assertEqual(gen1, 0)
        gen2 = self.publisher.publish(plan2)
        self.assertEqual(gen2, 1)

    def test_repeated_changes_with_gen_zero_monotonically_advance(self):
        """Every changed plan advances generation even when caller always passes 0."""
        plans = [
            RestorePlan(generation=0, model_key=ModelRestoreKey(unet_identity=f"u{i}"),
                        prefill_key=PrefillKey(prompt_bundle_hash=f"p{i}"))
            for i in range(4)
        ]
        for i, plan in enumerate(plans):
            gen = self.publisher.publish(plan)
            self.assertEqual(gen, i, f"Expected generation={i} for plan#{i}")
        self.assertEqual(self.coord.committed_generation, 3)

    def test_explicit_higher_generation_preserved(self):
        """When the caller supplies an explicit generation higher than the
        current one, it is preserved rather than overridden."""
        plan1 = RestorePlan(
            generation=0,
            model_key=ModelRestoreKey(unet_identity="u"),
            prefill_key=PrefillKey(prompt_bundle_hash="p1"),
        )
        plan2 = RestorePlan(
            generation=5,
            model_key=ModelRestoreKey(unet_identity="u2"),
            prefill_key=PrefillKey(prompt_bundle_hash="p2"),
        )
        gen1 = self.publisher.publish(plan1)
        self.assertEqual(gen1, 0)
        gen2 = self.publisher.publish(plan2)
        # Explicit 5 > current 0 → preserved
        self.assertEqual(gen2, 5)

    def test_monotonic_after_explicit_gen_then_default(self):
        """After an explicit high generation, a default gen=0 changed plan advances."""
        plan1 = RestorePlan(
            generation=10,
            model_key=ModelRestoreKey(unet_identity="u"),
            prefill_key=PrefillKey(prompt_bundle_hash="p1"),
        )
        plan2 = RestorePlan(
            generation=0,
            model_key=ModelRestoreKey(unet_identity="u2"),
            prefill_key=PrefillKey(prompt_bundle_hash="p2"),
        )
        gen1 = self.publisher.publish(plan1)
        self.assertEqual(gen1, 10)
        # Current is 10, incoming is 0 (behind) → advance to 11
        gen2 = self.publisher.publish(plan2)
        self.assertEqual(gen2, 11)

    def test_unchanged_plan_returns_current_gen_even_with_gen_zero(self):
        """An unchanged plan still returns the current generation without
        advancing, even when passed with generation=0."""
        plan1 = RestorePlan(
            generation=0,
            model_key=ModelRestoreKey(unet_identity="u"),
            prefill_key=PrefillKey(prompt_bundle_hash="p"),
        )
        plan2 = RestorePlan(
            generation=0,
            model_key=ModelRestoreKey(unet_identity="u"),
            prefill_key=PrefillKey(prompt_bundle_hash="p"),
        )
        gen1 = self.publisher.publish(plan1)
        self.assertEqual(gen1, 0)
        # Same plan, no-op check catches it → returns current gen 0 without writing
        gen2 = self.publisher.publish(plan2)
        self.assertEqual(gen2, 0)
        self.assertEqual(self.coord.metrics.write_count, 1)  # only first write


# ── Tests: end-to-end derivation → publication ──────────────────────────


class TestDeriveAndPublish(unittest.TestCase):
    """End-to-end: derive keys from workflow, publish, verify on re-read."""

    def setUp(self):
        self.volume = FakeVolume()
        self.coord = CommitCoordinator(self.volume)
        self.publisher = RestorePlanPublisher(self.coord)

    def test_derive_and_publish_round_trip(self):
        wf = _workflow_with_models(prompt="a beautiful landscape")
        model_key = derive_model_key(wf)
        prefill_key = derive_prefill_key(model_key, wf)

        plan = RestorePlan(
            generation=1,
            model_key=model_key,
            prefill_key=prefill_key,
            source_workflow_hash=stable_hash(wf),
        )

        gen = self.publisher.publish(plan)
        self.assertEqual(gen, 1)

        # Re-read from volume
        state = self.coord.read_state()
        self.assertIsNotNone(state)
        if state:
            restored = RestorePlan.from_dict(state["restore_plan"])
            self.assertEqual(restored.canonical_hash, plan.canonical_hash)

    def test_prompt_change_publishing(self):
        """Verify full cycle: change prompt → publish → plan differs."""
        wf1 = _workflow_with_models(prompt="cat")
        wf2 = _workflow_with_models(prompt="dog")

        mk = derive_model_key(wf1)
        pk1 = derive_prefill_key(mk, wf1)
        pk2 = derive_prefill_key(mk, wf2)

        plan1 = RestorePlan(generation=1, model_key=mk, prefill_key=pk1)
        plan2 = RestorePlan(generation=2, model_key=mk, prefill_key=pk2)

        gen1 = self.publisher.publish(plan1)
        gen2 = self.publisher.publish(plan2)

        self.assertEqual(gen1, 1)
        self.assertEqual(gen2, 2)
        # Plan hashes differ (prefill changed)
        self.assertNotEqual(plan1.canonical_hash, plan2.canonical_hash)

    def test_model_change_publication(self):
        """Verify full cycle: change model → publish → plan differs."""
        wf1 = _workflow_with_models(unet="model_a.safetensors")
        wf2 = _workflow_with_models(unet="model_b.safetensors")

        mk1 = derive_model_key(wf1)
        mk2 = derive_model_key(wf2)
        pk = PrefillKey(model_key=mk1, prompt_bundle_hash="p")

        plan1 = RestorePlan(generation=1, model_key=mk1, prefill_key=pk)
        plan2 = RestorePlan(generation=2, model_key=mk2, prefill_key=pk)

        gen1 = self.publisher.publish(plan1)
        gen2 = self.publisher.publish(plan2)

        self.assertNotEqual(gen1, gen2)
        # Plan hashes differ (model changed)
        self.assertNotEqual(plan1.canonical_hash, plan2.canonical_hash)


# ═══════════════════════════════════════════════════════════════════════
# Volatile-field no-op (different created_at/generation, same identity)
# ═══════════════════════════════════════════════════════════════════════


class TestVolatileFieldNoop(unittest.TestCase):
    """Equivalent identities with different volatile fields (created_at,
    generation) must NOT trigger a new write."""

    def setUp(self):
        self.volume = FakeVolume()
        self.coord = CommitCoordinator(self.volume)
        self.publisher = RestorePlanPublisher(self.coord)

    def test_different_created_at_same_identity_is_noop(self):
        """Two plans with identical model/prefill keys but different
        created_at return the same generation without writing again."""
        import time
        plan1 = RestorePlan(
            generation=0,
            model_key=ModelRestoreKey(unet_identity="u"),
            prefill_key=PrefillKey(prompt_bundle_hash="p"),
            created_at=1000.0,
        )
        plan2 = RestorePlan(
            generation=0,
            model_key=ModelRestoreKey(unet_identity="u"),
            prefill_key=PrefillKey(prompt_bundle_hash="p"),
            created_at=2000.0,
        )
        gen1 = self.publisher.publish(plan1)
        self.assertEqual(gen1, 0)
        write_count = self.coord.metrics.write_count

        # plan2 has same identity but different created_at — must be no-op
        gen2 = self.publisher.publish(plan2)
        self.assertEqual(gen2, 0, "Same identity must return same generation")
        self.assertEqual(self.coord.metrics.write_count, write_count,
                         "No additional write for same identity with different created_at")

    def test_different_generation_same_identity_is_noop(self):
        """Two plans with identical identity but different explicit generation
        values must not write a second time (the incoming generation is
        ignored for comparison)."""
        plan1 = RestorePlan(
            generation=5,
            model_key=ModelRestoreKey(unet_identity="u"),
            prefill_key=PrefillKey(prompt_bundle_hash="p"),
        )
        plan2 = RestorePlan(
            generation=99,
            model_key=ModelRestoreKey(unet_identity="u"),
            prefill_key=PrefillKey(prompt_bundle_hash="p"),
        )
        gen1 = self.publisher.publish(plan1)
        self.assertEqual(gen1, 5)
        write_count = self.coord.metrics.write_count

        # plan2 has same identity but gen=99 — must be no-op
        gen2 = self.publisher.publish(plan2)
        self.assertEqual(gen2, 5, "Identity unchanged returns existing generation")
        self.assertEqual(self.coord.metrics.write_count, write_count,
                         "No additional write for same identity with different generation")

    def test_changed_identity_still_advances_despite_same_volatile_fields(self):
        """When identity actually changes, the plan is written even if
        generation and created_at match the previous store exactly."""
        plan1 = RestorePlan(
            generation=1, created_at=500.0,
            model_key=ModelRestoreKey(unet_identity="u"),
            prefill_key=PrefillKey(prompt_bundle_hash="p1"),
        )
        plan2 = RestorePlan(
            generation=1, created_at=500.0,
            model_key=ModelRestoreKey(unet_identity="u2"),
            prefill_key=PrefillKey(prompt_bundle_hash="p2"),
        )
        gen1 = self.publisher.publish(plan1)
        self.assertEqual(gen1, 1)
        gen2 = self.publisher.publish(plan2)
        self.assertEqual(gen2, 2, "Changed identity must advance generation")



# ── Publisher identity-change flags ──────────────────────────────────────


class TestPublisherIdentityFlags(unittest.TestCase):
    """publish_with_metrics must report model/prefill identity change flags."""

    def setUp(self):
        self.volume = FakeVolume()
        self.coord = CommitCoordinator(self.volume)
        self.publisher = RestorePlanPublisher(self.coord)

    def test_first_publication_both_true(self):
        """First publication: model_identity_changed and prefill_identity_changed both true."""
        plan = RestorePlan(
            generation=1,
            model_key=ModelRestoreKey(unet_identity="u1"),
            prefill_key=PrefillKey(prompt_bundle_hash="p1"),
        )
        result = self.publisher.publish_with_metrics(plan)
        self.assertTrue(result["changed"])
        self.assertTrue(result["model_identity_changed"])
        self.assertTrue(result["prefill_identity_changed"])

    def test_identical_plan_both_false(self):
        """No-op: model_identity_changed and prefill_identity_changed both false."""
        plan = RestorePlan(
            generation=1,
            model_key=ModelRestoreKey(unet_identity="u1"),
            prefill_key=PrefillKey(prompt_bundle_hash="p1"),
        )
        self.publisher.publish_with_metrics(plan)
        result = self.publisher.publish_with_metrics(plan)
        self.assertFalse(result["changed"])
        self.assertFalse(result["model_identity_changed"])
        self.assertFalse(result["prefill_identity_changed"])

    def test_prompt_only_change(self):
        """Prompt-only change: model_identity_changed false, prefill true."""
        mk = ModelRestoreKey(unet_identity="u1")
        plan1 = RestorePlan(generation=1, model_key=mk,
                            prefill_key=PrefillKey(model_key=mk, prompt_bundle_hash="v1"))
        plan2 = RestorePlan(generation=2, model_key=mk,
                            prefill_key=PrefillKey(model_key=mk, prompt_bundle_hash="v2"))
        self.publisher.publish_with_metrics(plan1)
        result = self.publisher.publish_with_metrics(plan2)
        self.assertTrue(result["changed"])
        self.assertFalse(result["model_identity_changed"])
        self.assertTrue(result["prefill_identity_changed"])

    def test_model_only_change(self):
        """Model-only change: model_identity_changed true, prefill false."""
        plan1 = RestorePlan(generation=1,
                            model_key=ModelRestoreKey(unet_identity="u1"),
                            prefill_key=PrefillKey(prompt_bundle_hash="p1"))
        plan2 = RestorePlan(generation=2,
                            model_key=ModelRestoreKey(unet_identity="u2"),
                            prefill_key=PrefillKey(prompt_bundle_hash="p1"))
        self.publisher.publish_with_metrics(plan1)
        result = self.publisher.publish_with_metrics(plan2)
        self.assertTrue(result["changed"])
        self.assertTrue(result["model_identity_changed"])
        self.assertFalse(result["prefill_identity_changed"])

    def test_trace_contains_identity_flags(self):
        """Trace metadata must include model/prefill_identity_changed."""
        plan = RestorePlan(generation=1,
                           model_key=ModelRestoreKey(unet_identity="u1"),
                           prefill_key=PrefillKey(prompt_bundle_hash="p1"))
        result = self.publisher.publish_with_metrics(plan)
        meta = result["trace"]["metadata"]
        self.assertIn("model_identity_changed", meta)
        self.assertIn("prefill_identity_changed", meta)

    def test_noop_trace_identity_flags_false(self):
        """No-op trace metadata must have both flags false."""
        plan = RestorePlan(generation=1,
                           model_key=ModelRestoreKey(unet_identity="u1"),
                           prefill_key=PrefillKey(prompt_bundle_hash="p1"))
        self.publisher.publish_with_metrics(plan)
        result = self.publisher.publish_with_metrics(plan)
        meta = result["trace"]["metadata"]
        self.assertFalse(meta["model_identity_changed"])
        self.assertFalse(meta["prefill_identity_changed"])

    def test_metrics_keys_present(self):
        """Result dict must include model_identity_changed and prefill_identity_changed."""
        plan = RestorePlan(generation=1,
                           model_key=ModelRestoreKey(unet_identity="u1"),
                           prefill_key=PrefillKey(prompt_bundle_hash="p1"))
        result = self.publisher.publish_with_metrics(plan)
        self.assertIn("model_identity_changed", result)
        self.assertIn("prefill_identity_changed", result)


if __name__ == "__main__":
    unittest.main()
