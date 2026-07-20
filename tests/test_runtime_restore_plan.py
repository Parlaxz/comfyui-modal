"""Focused tests for restore_plan: DualCLIPLoader identity, safe generation, reload authority."""

from __future__ import annotations

import tempfile
import unittest
from unittest.mock import patch

from comfymodal_runtime.contracts import (
    ModelRestoreKey,
    PrefillKey,
    RestorePlan,
    TraceEvent,
)
from comfymodal_runtime.restore_plan import (
    _build_dual_clip_identity,
    _extract_model_references,
    _extract_prompt_texts,
    _infer_prompt_role,
    derive_model_key,
    derive_prefill_key,
    RestorePlanPublisher,
)
from comfymodal_runtime.runtime_state import (
    CommitCoordinator,
    FakeVolume,
    MountedStateVolume,
)
from comfymodal_runtime.trace import RuntimeTrace, merge_runtime_traces


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

    def test_modal_volume_publication_is_authoritative_and_synchronous(self):
        import comfymodal_runtime.modal_app as modal_app

        class FakeModalVolume:
            def __init__(self):
                self.reload_count = 0
                self.commit_count = 0

            def reload(self):
                self.reload_count += 1

            def commit(self):
                self.commit_count += 1

        with tempfile.TemporaryDirectory() as tmp:
            modal_volume = FakeModalVolume()
            resources = {"runtime_state_volume": modal_volume}
            plan = RestorePlan(generation=0, source_workflow_hash="wf-modal")
            with patch.object(modal_app, "_MODAL_RESOURCES", resources), \
                 patch.object(modal_app, "RUNTIME_STATE_PATH", tmp):
                first = modal_app._publish_restore_plan_impl(plan)
                second = modal_app._publish_restore_plan_impl(plan)
                from comfymodal_runtime.runtime_bootstrap import RuntimeBootstrap
                from comfymodal_runtime.runtime_executor import RuntimeExecutor
                entrypoint = modal_app.ModalRuntimeEntrypoint(
                    bootstrap=RuntimeBootstrap(
                        restore_gpu_state=lambda: None,
                        initialize_cuda=lambda: {"cuda_available": 1},
                    ),
                    executor=RuntimeExecutor(in_process_runner=lambda *_args: {"ok": True}),
                )
                restored = entrypoint.restore()

            self.assertEqual(first["status"], "published")
            self.assertEqual(first["generation"], 0)
            self.assertEqual(second["status"], "unchanged")
            self.assertEqual(second["generation"], 0)
            self.assertEqual(modal_volume.commit_count, 1)
            self.assertGreaterEqual(modal_volume.reload_count, 2)
            self.assertEqual(first["models_volume_write_count"], 0)
            self.assertEqual(first["models_volume_commit_count"], 0)
            self.assertIsNotNone(entrypoint._restore_plan)
            if entrypoint._restore_plan is not None:
                self.assertEqual(str(entrypoint._restore_plan.generation), "0")
            self.assertEqual(restored["status"], "restored")


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
        wf_a = {
            "2": {"class_type": "CLIPLoader", "inputs": {"clip_name": "clip.safetensors", "type": "flux"}},
            "6": {"class_type": "CLIPTextEncode", "inputs": {"text": "a dog", "clip": ["2", 0]}},
        }
        wf_b = {
            "2": {"class_type": "CLIPLoader", "inputs": {"clip_name": "clip.safetensors", "type": "flux"}},
            "6": {"class_type": "CLIPTextEncode", "inputs": {"text": "a cat", "clip": ["2", 0]}},
        }
        pa = derive_prefill_key(model_key, wf_a)
        pb = derive_prefill_key(model_key, wf_b)
        self.assertEqual(pa.model_key.stable_hash, pb.model_key.stable_hash)
        self.assertTrue(pa.encode_options["eligible"])
        self.assertNotEqual(pa.stable_hash, pb.stable_hash)


# ---------------------------------------------------------------------------
# _infer_prompt_role — default positive for unlabeled, explicit
# positive/negative preserved
# ---------------------------------------------------------------------------

class TestInferPromptRole(unittest.TestCase):
    """Verify _infer_prompt_role returns correct role strings.

    Unlabeled CLIPTextEncode nodes (no "positive" or "negative" in title)
    must default to "positive" so they are eligible when lane mode is
    "critical" (the default).  Explicit "positive" or "negative" in the
    title must still be respected.
    """

    def test_explicit_positive_in_title(self):
        node = {"title": "positive", "class_type": "CLIPTextEncode"}
        self.assertEqual(_infer_prompt_role(node), "positive")

    def test_explicit_positive_in_meta(self):
        node = {"class_type": "CLIPTextEncode", "_meta": {"title": "positive"}}
        self.assertEqual(_infer_prompt_role(node), "positive")

    def test_explicit_negative_in_title(self):
        node = {"title": "negative", "class_type": "CLIPTextEncode"}
        self.assertEqual(_infer_prompt_role(node), "negative")

    def test_explicit_negative_in_meta(self):
        node = {"class_type": "CLIPTextEncode", "_meta": {"title": "negative"}}
        self.assertEqual(_infer_prompt_role(node), "negative")

    def test_negative_takes_precedence_over_positive(self):
        """When both words appear, "negative" wins (conservative default)."""
        node = {"title": "negative positive", "class_type": "CLIPTextEncode"}
        self.assertEqual(_infer_prompt_role(node), "negative")

    def test_unlabeled_defaults_positive(self):
        """A CLIPTextEncode without positive/negative in title defaults to positive."""
        node = {"class_type": "CLIPTextEncode", "title": "CLIP Text Encode"}
        self.assertEqual(_infer_prompt_role(node), "positive")

    def test_unlabeled_no_title_defaults_positive(self):
        """A CLIPTextEncode with no title at all defaults to positive."""
        node = {"class_type": "CLIPTextEncode"}
        self.assertEqual(_infer_prompt_role(node), "positive")

    def test_unlabeled_empty_title_defaults_positive(self):
        """A CLIPTextEncode with empty title defaults to positive."""
        node = {"class_type": "CLIPTextEncode", "title": ""}
        self.assertEqual(_infer_prompt_role(node), "positive")

    def test_unlabeled_via_name_defaults_positive(self):
        """A node with a name (not title) but no positive/negative defaults positive."""
        node = {"class_type": "CLIPTextEncode", "name": "EncodePrompt"}
        self.assertEqual(_infer_prompt_role(node), "positive")

    def test_unlabeled_via_name_negative_explicit(self):
        """'negative' in name is still respected."""
        node = {"class_type": "CLIPTextEncode", "name": "NegativePrompt"}
        self.assertEqual(_infer_prompt_role(node), "negative")


class TestPrefillBundleRoleIntegration(unittest.TestCase):
    """Verify that the derived prefill bundle retains exact text/clip
    identity and correct role for unlabeled CLIPTextEncode entries."""

    def test_unlabeled_encode_gets_positive_role_in_bundle(self):
        """An unlabeled CLIPTextEncode must get role='positive' in the bundle."""
        workflow = {
            "2": {"class_type": "CLIPLoader", "inputs": {"clip_name": "clip.safetensors", "type": "flux"}},
            "6": {"class_type": "CLIPTextEncode", "inputs": {"text": "a dog", "clip": ["2", 0]}},
        }
        model_key = derive_model_key(workflow)
        prefill_key = derive_prefill_key(model_key, workflow)
        self.assertTrue(prefill_key.encode_options["eligible"])
        encodes = prefill_key.encode_options["encodes"]
        self.assertEqual(len(encodes), 1)
        entry = encodes[0]
        self.assertEqual(entry["role"], "positive",
                         "Unlabeled CLIPTextEncode must default to positive role")
        self.assertEqual(entry["text"], "a dog",
                         "Text identity must be preserved")
        self.assertEqual(entry["clip_connection"], ("2", 0),
                         "CLIP connection must be preserved")
        self.assertEqual(entry["node_class"], "CLIPTextEncode")
        self.assertEqual(entry["node_id"], "6")

    def test_negative_title_encode_gets_negative_role_in_bundle(self):
        """A CLIPTextEncode with 'negative' in title gets role='negative'."""
        workflow = {
            "2": {"class_type": "CLIPLoader", "inputs": {"clip_name": "clip.safetensors", "type": "flux"}},
            "7": {"class_type": "CLIPTextEncode", "title": "negative",
                  "inputs": {"text": "bad stuff", "clip": ["2", 0]}},
        }
        model_key = derive_model_key(workflow)
        prefill_key = derive_prefill_key(model_key, workflow)
        self.assertTrue(prefill_key.encode_options["eligible"])
        encodes = prefill_key.encode_options["encodes"]
        self.assertEqual(len(encodes), 1)
        entry = encodes[0]
        self.assertEqual(entry["role"], "negative",
                         "Explicit 'negative' title must yield negative role")
        self.assertEqual(entry["text"], "bad stuff")

    def test_positive_title_encode_gets_positive_role_in_bundle(self):
        """A CLIPTextEncode with 'positive' in title gets role='positive'."""
        workflow = {
            "2": {"class_type": "CLIPLoader", "inputs": {"clip_name": "clip.safetensors", "type": "flux"}},
            "8": {"class_type": "CLIPTextEncode", "title": "positive",
                  "inputs": {"text": "good stuff", "clip": ["2", 0]}},
        }
        model_key = derive_model_key(workflow)
        prefill_key = derive_prefill_key(model_key, workflow)
        self.assertTrue(prefill_key.encode_options["eligible"])
        encodes = prefill_key.encode_options["encodes"]
        self.assertEqual(len(encodes), 1)
        entry = encodes[0]
        self.assertEqual(entry["role"], "positive",
                         "Explicit 'positive' title must yield positive role")
        self.assertEqual(entry["text"], "good stuff")

    def test_mixed_positive_and_unlabeled_produces_two_entries(self):
        """Both a positive-titled and an unlabeled encode are included with correct roles."""
        workflow = {
            "2": {"class_type": "CLIPLoader", "inputs": {"clip_name": "clip.safetensors", "type": "flux"}},
            "6": {"class_type": "CLIPTextEncode",
                  "inputs": {"text": "a dog", "clip": ["2", 0]}},
            "7": {"class_type": "CLIPTextEncode", "title": "negative",
                  "inputs": {"text": "a cat", "clip": ["2", 0]}},
        }
        model_key = derive_model_key(workflow)
        prefill_key = derive_prefill_key(model_key, workflow)
        self.assertTrue(prefill_key.encode_options["eligible"])
        encodes = prefill_key.encode_options["encodes"]
        self.assertEqual(len(encodes), 2)
        roles = {e["node_id"]: e["role"] for e in encodes}
        self.assertEqual(roles["6"], "positive",
                         "Unlabeled node_id=6 must default to positive")
        self.assertEqual(roles["7"], "negative",
                         "Negative-titled node_id=7 must be negative")


# ---------------------------------------------------------------------------
# Publication measurement keys (no Modal required)
# ---------------------------------------------------------------------------

class TestPublicationMeasurementKeys(unittest.TestCase):
    """Verify publish_with_metrics returns all granular measurements."""

    def setUp(self):
        self.volume = FakeVolume()
        self.coord = CommitCoordinator(self.volume)
        self.publisher = RestorePlanPublisher(self.coord)

    def test_changed_publish_contains_all_measurement_keys(self):
        plan = RestorePlan(generation=1, model_key=ModelRestoreKey(unet_identity="u1"))
        result = self.publisher.publish_with_metrics(plan)
        expected_keys = {
            "changed", "generation",
            "reload_ms", "compare_ms", "write_ms", "commit_ms",
            "bytes_written", "state_path", "trace",
        }
        self.assertTrue(expected_keys.issubset(result.keys()),
                        f"Missing keys: {expected_keys - result.keys()}")
        self.assertTrue(result["changed"])
        self.assertIsInstance(result["reload_ms"], float)
        self.assertIsInstance(result["compare_ms"], float)
        self.assertIsInstance(result["write_ms"], float)
        self.assertIsInstance(result["commit_ms"], float)
        self.assertIsInstance(result["bytes_written"], int)
        self.assertGreater(result["bytes_written"], 0,
                           "Changed plan must write bytes")

    def test_unchanged_publish_all_measurement_keys(self):
        plan = RestorePlan(generation=1, model_key=ModelRestoreKey(unet_identity="u1"))
        self.publisher.publish_with_metrics(plan)
        # Publish same plan again → no-op
        result = self.publisher.publish_with_metrics(plan)
        self.assertFalse(result["changed"])
        self.assertEqual(result["bytes_written"], 0)
        self.assertEqual(result["write_ms"], 0.0)
        self.assertEqual(result["commit_ms"], 0.0)
        for key in ("reload_ms", "compare_ms"):
            self.assertIsInstance(result[key], float)

    def test_trace_present_and_structured(self):
        plan = RestorePlan(generation=1, model_key=ModelRestoreKey(unet_identity="u1"))
        result = self.publisher.publish_with_metrics(plan)
        self.assertIn("trace", result)
        trace = result["trace"]
        # RuntimeTrace.to_dict() shape
        self.assertIn("trace_id", trace)
        self.assertIn("events", trace)
        self.assertIn("metadata", trace)
        self.assertGreater(len(trace["events"]), 0)

    def test_changed_trace_contains_write_and_commit_events(self):
        plan = RestorePlan(generation=1, model_key=ModelRestoreKey(unet_identity="u1"))
        result = self.publisher.publish_with_metrics(plan)
        event_names = [e["name"] for e in result["trace"]["events"]]
        self.assertIn("publish_state_read", event_names)
        self.assertIn("publish_compare", event_names)
        self.assertIn("publish_write", event_names)
        self.assertIn("publish_commit", event_names)
        self.assertNotIn("publish_noop", event_names)

    def test_unchanged_trace_has_noop_event(self):
        plan = RestorePlan(generation=1, model_key=ModelRestoreKey(unet_identity="u1"))
        self.publisher.publish_with_metrics(plan)
        result = self.publisher.publish_with_metrics(plan)
        event_names = [e["name"] for e in result["trace"]["events"]]
        self.assertIn("publish_noop", event_names)
        self.assertNotIn("publish_write", event_names)
        self.assertNotIn("publish_commit", event_names)

    def test_trace_has_measurement_values_in_metadata(self):
        plan = RestorePlan(generation=1, model_key=ModelRestoreKey(unet_identity="u1"))
        result = self.publisher.publish_with_metrics(plan)
        for event in result["trace"]["events"]:
            self.assertIsInstance(event["metadata"], dict)
        write_event = next(
            e for e in result["trace"]["events"]
            if e["name"] == "publish_write"
        )
        self.assertIn("write_ms", write_event["metadata"])
        self.assertIn("bytes_written", write_event["metadata"])
        self.assertGreater(write_event["metadata"]["bytes_written"], 0)

    def test_trace_mergeable_with_other_traces(self):
        """The publication trace can be merged with another RuntimeTrace."""
        plan = RestorePlan(generation=1, model_key=ModelRestoreKey(unet_identity="u1"))
        pub_result = self.publisher.publish_with_metrics(plan)
        pub_trace = RuntimeTrace(
            process="publisher",
            trace_id=pub_result["trace"]["trace_id"],
        )
        pub_trace.extend(
            TraceEvent.from_dict(e) for e in pub_result["trace"]["events"]
        )
        exec_trace = RuntimeTrace(process="remote")
        exec_trace.emit("graph_execution_start", phase="execution")
        merged = merge_runtime_traces(pub_trace, exec_trace)
        merged_names = {e.name for e in merged.events}
        self.assertIn("publish_write", merged_names)
        self.assertIn("graph_execution_start", merged_names)
        # Exactly one of each — no duplicates
        self.assertEqual(
            sum(1 for e in merged.events if e.name == "publish_write"), 1,
        )


# ---------------------------------------------------------------------------
# merge_runtime_traces behavior tests
# ---------------------------------------------------------------------------

class TestMergeRuntimeTraces(unittest.TestCase):
    """Direct behavior tests for merge_runtime_traces."""

    def test_remote_events_survive(self):
        local = RuntimeTrace(process="local")
        local.emit("local_step", phase="test")
        remote = RuntimeTrace(process="remote")
        remote.emit("remote_step", phase="test")
        merged = merge_runtime_traces(local, remote)
        names = {e.name for e in merged.events}
        self.assertIn("local_step", names)
        self.assertIn("remote_step", names)

    def test_exact_duplicates_removed(self):
        trace = RuntimeTrace(process="local")
        trace.emit("event_a", phase="test")
        trace.emit("event_b", phase="test")
        # Merge trace with itself — duplicates must be removed
        merged = merge_runtime_traces(trace, trace)
        self.assertEqual(len(merged.events), 2,
                         "Exact duplicates should be removed")

    def test_distinct_events_survive_despite_partial_overlap(self):
        t1 = RuntimeTrace(process="local")
        t1.emit("common", phase="test")
        t2 = RuntimeTrace(process="remote")
        t2.emit("common", phase="test")
        t2.emit("unique_to_remote", phase="test")
        merged = merge_runtime_traces(t1, t2)
        names = {e.name for e in merged.events}
        self.assertIn("common", names)
        self.assertIn("unique_to_remote", names)
        # "common" events from different processes have different wall
        # timestamps and process fields → they are NOT exact duplicates
        # and must both survive.
        self.assertEqual(len(merged.events), 3,
                         "Different-process common events are distinct")

    def test_cross_process_sorted_by_wall_time(self):
        """Events from different processes are sorted solely by wall_unix_ns."""
        local_trace = RuntimeTrace(process="local")
        local_trace._events.append(TraceEvent(
            name="later_local", process="local", phase="test",
            wall_unix_ns=2000, monotonic_ns=0,
        ))
        remote_trace = RuntimeTrace(process="remote")
        remote_trace._events.append(TraceEvent(
            name="earlier_remote", process="remote", phase="test",
            wall_unix_ns=1000, monotonic_ns=0,
        ))
        merged = merge_runtime_traces(local_trace, remote_trace)
        wall_times = [e.wall_unix_ns for e in merged.events]
        self.assertEqual(wall_times, sorted(wall_times),
                         "Events must be sorted by wall time")
        # The remote event (earlier) should come first
        self.assertEqual(merged.events[0].name, "earlier_remote")
        self.assertEqual(merged.events[1].name, "later_local")

    def test_restore_and_execution_traces_coexist(self):
        restore = RuntimeTrace(process="remote")
        restore.emit("restore_start", phase="restore")
        exec_trace = RuntimeTrace(process="remote")
        exec_trace.emit("execution_done", phase="execution")
        merged = merge_runtime_traces(restore, exec_trace)
        phases = {e.phase for e in merged.events}
        self.assertIn("restore", phases)
        self.assertIn("execution", phases)
        self.assertEqual(len(merged.events), 2)

    def test_mapping_input_normalization(self):
        """Mapping (dict) inputs are normalized through from_legacy."""
        trace = RuntimeTrace(process="remote")
        trace.emit("test_event", phase="test")
        as_dict = trace.to_dict()
        merged = merge_runtime_traces(as_dict)
        self.assertEqual(len(merged.events), 1)
        self.assertEqual(merged.events[0].name, "test_event")

    def test_metadata_merged_in_order(self):
        """Metadata from later traces overrides earlier keys."""
        t1 = RuntimeTrace(process="local")
        t1.set_metadata(phase="first", keep="me")
        t2 = RuntimeTrace(process="remote")
        t2.set_metadata(phase="second")
        merged = merge_runtime_traces(t1, t2)
        self.assertEqual(merged._metadata.get("keep"), "me")
        self.assertEqual(merged._metadata.get("phase"), "second")

    def test_event_count_correct_with_mixed_none(self):
        t1 = RuntimeTrace(process="local")
        t1.emit("a", phase="test")
        merged = merge_runtime_traces(t1, None, t1)
        self.assertEqual(len(merged.events), 1)


if __name__ == "__main__":
    unittest.main()
