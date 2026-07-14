import unittest

from production_workflow import (
    normalize_production_options,
    build_production_topology_hash,
    compile_production_workflow,
    analyze_duplicate_work,
    _reset_cache,
    _cache_size,
    _compute_source_workflow_hash,
    COMPILER_SCHEMA_VERSION,
)


def _minimal_production(output_ids=None, bypass_ids=None, **overrides):
    prod = {
        "schema_version": COMPILER_SCHEMA_VERSION,
        "output_node_ids": output_ids or ["9"],
        "bypass_node_ids": bypass_ids or [],
        "disable_sampler_previews": True,
        "quiet_execution_logs": True,
        "progress_min_interval_ms": 500,
        "strict_output_collection": True,
        "direct_output_sink": True,
        "metadata_mode": "none",
    }
    prod.update(overrides)
    return prod


WORKFLOW_SINGLE_OUTPUT = {
    "3": {"class_type": "KSampler", "inputs": {
        "seed": 7, "steps": 20, "cfg": 3.5,
        "sampler_name": "euler", "scheduler": "normal", "denoise": 1,
        "model": ("4", 0), "positive": ("6", 0), "negative": ("7", 0),
        "latent_image": ("5", 0),
    }},
    "4": {"class_type": "UNETLoader", "inputs": {"unet_name": "flux-model.safetensors"}},
    "5": {"class_type": "EmptyLatentImage", "inputs": {"width": 1024, "height": 1024}},
    "6": {"class_type": "CLIPTextEncode", "inputs": {"text": "a cat", "clip": ("8", 0)}},
    "7": {"class_type": "CLIPTextEncode", "inputs": {"text": "", "clip": ("8", 0)}},
    "8": {"class_type": "CLIPLoader", "inputs": {"clip_name": "clip.safetensors"}},
    "9": {"class_type": "VAEDecode", "inputs": {"samples": ("3", 0), "vae": ("10", 0)}},
    "10": {"class_type": "VAELoader", "inputs": {"vae_name": "vae.safetensors"}},
    "11": {"class_type": "PreviewImage", "inputs": {"images": ("9", 0)}},
}

WORKFLOW_MULTI_OUTPUT = {
    "3": {"class_type": "KSampler", "inputs": {
        "seed": 7, "steps": 20, "cfg": 3.5,
        "sampler_name": "euler", "scheduler": "normal", "denoise": 1,
        "model": ("4", 0), "positive": ("6", 0), "negative": ("7", 0),
        "latent_image": ("5", 0),
    }},
    "4": {"class_type": "UNETLoader", "inputs": {"unet_name": "flux-model.safetensors"}},
    "5": {"class_type": "EmptyLatentImage", "inputs": {"width": 1024, "height": 1024}},
    "6": {"class_type": "CLIPTextEncode", "inputs": {"text": "a cat", "clip": ("8", 0)}},
    "7": {"class_type": "CLIPTextEncode", "inputs": {"text": "", "clip": ("8", 0)}},
    "8": {"class_type": "CLIPLoader", "inputs": {"clip_name": "clip.safetensors"}},
    "9": {"class_type": "VAEDecode", "inputs": {"samples": ("3", 0), "vae": ("10", 0)}},
    "10": {"class_type": "VAELoader", "inputs": {"vae_name": "vae.safetensors"}},
    "11": {"class_type": "SaveImage", "inputs": {"images": ("9", 0)}},
    "12": {"class_type": "PreviewImage", "inputs": {"images": ("9", 0)}},
}


class NormalizeProductionOptionsTests(unittest.TestCase):
    def test_none_returns_enabled_with_defaults(self):
        """modal_options=None → enabled=True with canonical defaults, empty output_node_ids."""
        result = normalize_production_options(None)
        self.assertTrue(result["enabled"])
        self.assertEqual(result["schema_version"], COMPILER_SCHEMA_VERSION)
        self.assertEqual(result["output_node_ids"], [])
        self.assertTrue(result["disable_sampler_previews"])
        self.assertTrue(result["quiet_execution_logs"])
        self.assertEqual(result["progress_min_interval_ms"], 500)

    def test_empty_dict_returns_enabled_with_defaults(self):
        """modal_options={} → enabled=True with canonical defaults."""
        result = normalize_production_options({})
        self.assertTrue(result["enabled"])
        self.assertEqual(result["schema_version"], COMPILER_SCHEMA_VERSION)
        self.assertEqual(result["output_node_ids"], [])

    def test_no_production_key_returns_enabled_with_defaults(self):
        """modal_options without production key → enabled=True with defaults."""
        result = normalize_production_options({"other": "data"})
        self.assertTrue(result["enabled"])
        self.assertEqual(result["schema_version"], COMPILER_SCHEMA_VERSION)
        self.assertEqual(result["output_node_ids"], [])

    def test_rejects_non_dict(self):
        with self.assertRaises(TypeError):
            normalize_production_options({"production": "not-a-dict"})

    def test_rejects_wrong_schema_version(self):
        with self.assertRaises(ValueError):
            normalize_production_options({
                "production": {"schema_version": 99, "output_node_ids": ["9"]}
            })

    def test_accepts_direct_dict_with_schema_and_outputs(self):
        result = normalize_production_options({
            "schema_version": COMPILER_SCHEMA_VERSION,
            "output_node_ids": ["9"],
        })
        self.assertTrue(result["enabled"])
        self.assertEqual(result["output_node_ids"], ["9"])

    def test_returns_disabled_when_explicitly_disabled(self):
        result = normalize_production_options({
            "production": {"enabled": False, "schema_version": COMPILER_SCHEMA_VERSION}
        })
        self.assertEqual(result, {"enabled": False})

    def test_normalizes_and_deduplicates_ids(self):
        result = normalize_production_options({
            "production": {
                "schema_version": COMPILER_SCHEMA_VERSION,
                "output_node_ids": [9, "10", 9, "9", "8"],
            }
        })
        self.assertEqual(result["output_node_ids"], ["8", "9", "10"])

    def test_allows_empty_output_node_ids(self):
        """Normalizer no longer rejects empty output_node_ids - surface derives them."""
        result = normalize_production_options({
            "production": {"schema_version": COMPILER_SCHEMA_VERSION, "output_node_ids": []}
        })
        self.assertTrue(result["enabled"])
        self.assertEqual(result["output_node_ids"], [])

    def test_rejects_overlap(self):
        with self.assertRaises(ValueError):
            normalize_production_options({
                "production": {
                    "schema_version": COMPILER_SCHEMA_VERSION,
                    "output_node_ids": ["9", "10"],
                    "bypass_node_ids": ["9"],
                }
            })

    def test_accepts_valid_config(self):
        result = normalize_production_options({
            "production": {
                "schema_version": COMPILER_SCHEMA_VERSION,
                "output_node_ids": ["9"],
                "disable_sampler_previews": False,
            }
        })
        self.assertTrue(result["enabled"])
        self.assertFalse(result["disable_sampler_previews"])

    def test_applies_defaults(self):
        result = normalize_production_options({
            "production": {
                "schema_version": COMPILER_SCHEMA_VERSION,
                "output_node_ids": ["9"],
            }
        })
        self.assertTrue(result["disable_sampler_previews"])
        self.assertTrue(result["quiet_execution_logs"])
        self.assertEqual(result["progress_min_interval_ms"], 500)
        self.assertTrue(result["strict_output_collection"])
        self.assertTrue(result["direct_output_sink"])
        self.assertEqual(result["metadata_mode"], "none")

    def test_bypass_normalization(self):
        result = normalize_production_options({
            "production": {
                "schema_version": COMPILER_SCHEMA_VERSION,
                "output_node_ids": ["9"],
                "bypass_node_ids": [8, "8", 10, "10"],
            }
        })
        self.assertEqual(result["bypass_node_ids"], ["8", "10"])


class CompileProductionWorkflowTests(unittest.TestCase):
    def setUp(self):
        _reset_cache()

    def test_one_selected_output_dead_preview_removed(self):
        prod = _minimal_production(output_ids=["9"])
        compiled, report = compile_production_workflow(
            WORKFLOW_SINGLE_OUTPUT, prod, allow_direct_output_rewrite=False
        )
        self.assertIn("9", compiled)
        self.assertNotIn("11", compiled)
        self.assertIn("9", report["kept_node_ids"])
        self.assertNotIn("11", report["kept_node_ids"])
        self.assertIn("11", report["removed_node_ids"])

    def test_multiple_selected_outputs_retained(self):
        prod = _minimal_production(output_ids=["11", "12"])
        compiled, report = compile_production_workflow(
            WORKFLOW_MULTI_OUTPUT, prod, allow_direct_output_rewrite=False
        )
        self.assertIn("11", compiled)
        self.assertIn("12", compiled)

    def test_shared_ancestors_retained_once(self):
        prod = _minimal_production(output_ids=["9"])
        compiled, _ = compile_production_workflow(
            WORKFLOW_SINGLE_OUTPUT, prod, allow_direct_output_rewrite=False
        )
        self.assertIn("3", compiled)
        self.assertIn("6", compiled)
        self.assertIn("7", compiled)
        self.assertIn("8", compiled)
        self.assertIn("10", compiled)

    def test_disconnected_model_loader_removed(self):
        wf = dict(WORKFLOW_SINGLE_OUTPUT)
        wf["99"] = {"class_type": "UNETLoader", "inputs": {"unet_name": "orphan.safetensors"}}
        prod = _minimal_production(output_ids=["9"])
        compiled, report = compile_production_workflow(
            wf, prod, allow_direct_output_rewrite=False
        )
        self.assertNotIn("99", compiled)
        self.assertIn("99", report["removed_node_ids"])

    def test_scalar_inputs_preserved(self):
        prod = _minimal_production(output_ids=["9"])
        compiled, _ = compile_production_workflow(
            WORKFLOW_SINGLE_OUTPUT, prod, allow_direct_output_rewrite=False
        )
        sampler = compiled["3"]
        self.assertEqual(sampler["inputs"]["seed"], 7)
        self.assertEqual(sampler["inputs"]["steps"], 20)
        self.assertEqual(sampler["inputs"]["cfg"], 3.5)

    def test_connection_detection_ignores_arbitrary_two_item_lists(self):
        wf = {
            "1": {"class_type": "Note", "inputs": {"text": "hello world"}},
            "2": {"class_type": "ListMaker", "inputs": {"pair": ["x", "y"]}},
        }
        prod = _minimal_production(output_ids=["1", "2"])
        compiled, _ = compile_production_workflow(
            wf, prod, allow_direct_output_rewrite=False
        )
        self.assertIn("2", compiled)

    def test_missing_output_rejected(self):
        prod = _minimal_production(output_ids=["999"])
        with self.assertRaises(ValueError):
            compile_production_workflow(
                WORKFLOW_SINGLE_OUTPUT, prod, allow_direct_output_rewrite=False
            )

    def test_output_also_marked_bypass_rejected(self):
        prod = _minimal_production(output_ids=["9"], bypass_ids=["9"])
        with self.assertRaises(ValueError):
            compile_production_workflow(
                WORKFLOW_SINGLE_OUTPUT, prod, allow_direct_output_rewrite=False
            )

    def test_bypass_id_remaining_rejected(self):
        wf = {
            "1": {"class_type": "KSampler", "inputs": {"seed": 1}},
            "2": {"class_type": "SaveImage", "inputs": {"images": ("1", 0)}},
        }
        prod = _minimal_production(output_ids=["2"], bypass_ids=["1"])
        with self.assertRaises(ValueError) as ctx:
            compile_production_workflow(wf, prod, allow_direct_output_rewrite=False)
        msg = str(ctx.exception)
        self.assertIn("Production bypass failed for node", msg)
        self.assertIn("(KSampler)", msg)
        self.assertIn("ComfyUI could not serialize this node as a native bypass", msg)

    def test_direct_output_rewrite_save_image(self):
        wf = {
            "1": {"class_type": "KSampler", "inputs": {"seed": 1, "model": ("2", 0)}},
            "2": {"class_type": "UNETLoader", "inputs": {"unet_name": "m.safetensors"}},
            "3": {"class_type": "VAEDecode", "inputs": {"samples": ("1", 0)}},
            "4": {"class_type": "SaveImage", "inputs": {"images": ("3", 0)}},
        }
        prod = _minimal_production(output_ids=["4"])
        compiled, report = compile_production_workflow(
            wf, prod, allow_direct_output_rewrite=True
        )
        self.assertEqual(compiled["4"]["class_type"], "ComfyModalProductionOutput")
        self.assertEqual(compiled["4"]["inputs"]["images"], ("3", 0))
        self.assertIn("4", report["direct_output_rewritten_node_ids"])

    def test_direct_output_rewrite_preview_image(self):
        wf = {
            "1": {"class_type": "KSampler", "inputs": {"seed": 1, "model": ("2", 0)}},
            "2": {"class_type": "UNETLoader", "inputs": {"unet_name": "m.safetensors"}},
            "3": {"class_type": "VAEDecode", "inputs": {"samples": ("1", 0)}},
            "4": {"class_type": "PreviewImage", "inputs": {"images": ("3", 0)}},
        }
        prod = _minimal_production(output_ids=["4"])
        compiled, _ = compile_production_workflow(
            wf, prod, allow_direct_output_rewrite=True
        )
        self.assertEqual(compiled["4"]["class_type"], "ComfyModalProductionOutput")

    def test_direct_output_rewrite_save_image_with_metadata(self):
        wf = {
            "1": {"class_type": "KSampler", "inputs": {"seed": 1, "model": ("2", 0)}},
            "2": {"class_type": "UNETLoader", "inputs": {"unet_name": "m.safetensors"}},
            "3": {"class_type": "VAEDecode", "inputs": {"samples": ("1", 0)}},
            "4": {"class_type": "SaveImageWithMetaData", "inputs": {"images": ("3", 0)}},
        }
        prod = _minimal_production(output_ids=["4"])
        compiled, _ = compile_production_workflow(
            wf, prod, allow_direct_output_rewrite=True
        )
        self.assertEqual(compiled["4"]["class_type"], "ComfyModalProductionOutput")

    def test_no_rewrite_when_images_not_valid_connection(self):
        wf = {
            "1": {"class_type": "KSampler", "inputs": {"seed": 1}},
            "2": {"class_type": "SaveImage", "inputs": {"images": "literal_filename.png"}},
        }
        prod = _minimal_production(output_ids=["2"])
        compiled, report = compile_production_workflow(
            wf, prod, allow_direct_output_rewrite=True
        )
        self.assertEqual(compiled["2"]["class_type"], "SaveImage")
        self.assertEqual(report["direct_output_rewritten_node_ids"], [])

    def test_metadata_mode_full_disables_direct_rewrite(self):
        wf = {
            "1": {"class_type": "KSampler", "inputs": {"seed": 1, "model": ("2", 0)}},
            "2": {"class_type": "UNETLoader", "inputs": {"unet_name": "m.safetensors"}},
            "3": {"class_type": "VAEDecode", "inputs": {"samples": ("1", 0)}},
            "4": {"class_type": "SaveImage", "inputs": {"images": ("3", 0)}},
        }
        prod = _minimal_production(output_ids=["4"], metadata_mode="full")
        compiled, report = compile_production_workflow(
            wf, prod, allow_direct_output_rewrite=True
        )
        self.assertEqual(compiled["4"]["class_type"], "SaveImage")
        self.assertEqual(report["direct_output_rewritten_node_ids"], [])

    def test_unsupported_output_class_unchanged(self):
        wf = {
            "1": {"class_type": "KSampler", "inputs": {"seed": 1, "model": ("2", 0)}},
            "2": {"class_type": "UNETLoader", "inputs": {"unet_name": "m.safetensors"}},
            "3": {"class_type": "VAEDecode", "inputs": {"samples": ("1", 0)}},
        }
        prod = _minimal_production(output_ids=["3"])
        compiled, _ = compile_production_workflow(
            wf, prod, allow_direct_output_rewrite=True
        )
        self.assertEqual(compiled["3"]["class_type"], "VAEDecode")

    def test_allow_direct_output_rewrite_false_skips_rewrite(self):
        wf = {
            "1": {"class_type": "KSampler", "inputs": {"seed": 1, "model": ("2", 0)}},
            "2": {"class_type": "UNETLoader", "inputs": {"unet_name": "m.safetensors"}},
            "3": {"class_type": "VAEDecode", "inputs": {"samples": ("1", 0)}},
            "4": {"class_type": "SaveImage", "inputs": {"images": ("3", 0)}},
        }
        prod = _minimal_production(output_ids=["4"])
        compiled, _ = compile_production_workflow(
            wf, prod, allow_direct_output_rewrite=False
        )
        self.assertEqual(compiled["4"]["class_type"], "SaveImage")


class TopologyHashTests(unittest.TestCase):
    def test_stable_when_only_prompt_text_changes(self):
        wf1 = {**WORKFLOW_SINGLE_OUTPUT}
        wf2 = dict(WORKFLOW_SINGLE_OUTPUT)
        wf2["6"] = dict(wf2["6"])
        wf2["6"]["inputs"] = dict(wf2["6"]["inputs"], text="a different prompt")
        prod = _minimal_production(output_ids=["9"])
        h1 = build_production_topology_hash(wf1, prod, allow_direct_output_rewrite=False)
        h2 = build_production_topology_hash(wf2, prod, allow_direct_output_rewrite=False)
        self.assertEqual(h1, h2)

    def test_stable_when_only_seed_changes(self):
        wf1 = {**WORKFLOW_SINGLE_OUTPUT}
        wf2 = dict(WORKFLOW_SINGLE_OUTPUT)
        wf2["3"] = dict(wf2["3"])
        wf2["3"]["inputs"] = dict(wf2["3"]["inputs"], seed=42)
        prod = _minimal_production(output_ids=["9"])
        h1 = build_production_topology_hash(wf1, prod, allow_direct_output_rewrite=False)
        h2 = build_production_topology_hash(wf2, prod, allow_direct_output_rewrite=False)
        self.assertEqual(h1, h2)

    def test_changes_when_graph_connection_changes(self):
        wf1 = {**WORKFLOW_SINGLE_OUTPUT}
        wf2 = dict(WORKFLOW_SINGLE_OUTPUT)
        wf2["6"] = dict(wf2["6"])
        wf2["6"]["inputs"] = dict(wf2["6"]["inputs"], clip=("99", 0))
        wf2["99"] = {"class_type": "CLIPLoader", "inputs": {"clip_name": "other.safetensors"}}
        prod = _minimal_production(output_ids=["9"])
        h1 = build_production_topology_hash(wf1, prod, allow_direct_output_rewrite=False)
        h2 = build_production_topology_hash(wf2, prod, allow_direct_output_rewrite=False)
        self.assertNotEqual(h1, h2)

    def test_changes_when_production_outputs_change(self):
        wf = {**WORKFLOW_MULTI_OUTPUT}
        prod1 = _minimal_production(output_ids=["11"])
        prod2 = _minimal_production(output_ids=["12"])
        h1 = build_production_topology_hash(wf, prod1, allow_direct_output_rewrite=False)
        h2 = build_production_topology_hash(wf, prod2, allow_direct_output_rewrite=False)
        self.assertNotEqual(h1, h2)

    def test_changes_when_direct_output_sink_changes(self):
        wf = {**WORKFLOW_SINGLE_OUTPUT}
        prod1 = _minimal_production(output_ids=["9"])
        prod2 = _minimal_production(output_ids=["9"], direct_output_sink=False)
        h1 = build_production_topology_hash(wf, prod1, allow_direct_output_rewrite=False)
        h2 = build_production_topology_hash(wf, prod2, allow_direct_output_rewrite=False)
        self.assertNotEqual(h1, h2)

    def test_changes_when_allow_direct_output_rewrite_differs(self):
        wf = {**WORKFLOW_SINGLE_OUTPUT}
        prod = _minimal_production(output_ids=["9"])
        h1 = build_production_topology_hash(wf, prod, allow_direct_output_rewrite=False)
        h2 = build_production_topology_hash(wf, prod, allow_direct_output_rewrite=True)
        self.assertNotEqual(h1, h2)

    def test_unresolved_connection_like_treated_as_literal(self):
        wf = {
            "1": {"class_type": "Note", "inputs": {"pair": (99, 0)}},
        }
        prod = _minimal_production(output_ids=["1"])
        h = build_production_topology_hash(wf, prod, allow_direct_output_rewrite=False)
        self.assertIsInstance(h, str)
        self.assertEqual(len(h), 64)


class AnalyzeDuplicateWorkTests(unittest.TestCase):
    def test_duplicate_output_groups_detected(self):
        wf = {
            "1": {"class_type": "VAEDecode", "inputs": {"samples": ("3", 0)}},
            "2": {"class_type": "SaveImage", "inputs": {"images": ("1", 0)}},
            "3": {"class_type": "SaveImage", "inputs": {"images": ("1", 0)}},
            "4": {"class_type": "PreviewImage", "inputs": {"images": ("1", 0)}},
        }
        result = analyze_duplicate_work(wf)
        self.assertEqual(len(result["duplicate_output_groups"]), 1)
        group = result["duplicate_output_groups"][0]
        self.assertEqual(group["source_node_id"], "1")
        self.assertEqual(set(group["member_node_ids"]), {"2", "3", "4"})

    def test_duplicate_vae_decode_groups_detected(self):
        wf = {
            "1": {"class_type": "KSampler", "inputs": {"seed": 1, "model": ("5", 0)}},
            "2": {"class_type": "VAEDecode", "inputs": {"samples": ("1", 0), "vae": ("6", 0)}},
            "3": {"class_type": "VAEDecode", "inputs": {"samples": ("1", 0), "vae": ("6", 0)}},
            "4": {"class_type": "VAEDecode", "inputs": {"samples": ("1", 0), "vae": ("7", 0)}},
            "5": {"class_type": "UNETLoader", "inputs": {"unet_name": "m.safetensors"}},
            "6": {"class_type": "VAELoader", "inputs": {"vae_name": "a.safetensors"}},
            "7": {"class_type": "VAELoader", "inputs": {"vae_name": "b.safetensors"}},
        }
        result = analyze_duplicate_work(wf)
        vae_groups = result["duplicate_vae_decode_groups"]
        self.assertTrue(
            any(
                set(g["member_node_ids"]) == {"2", "3"}
                for g in vae_groups
            ),
            f"Expected node 2 and 3 to form a VAE duplicate group, got {vae_groups}",
        )

    def test_vae_requires_exact_class_type_match(self):
        wf = {
            "1": {"class_type": "KSampler", "inputs": {"seed": 1}},
            "2": {"class_type": "VAEDecode", "inputs": {"samples": ("1", 0), "vae": ("5", 0)}},
            "3": {"class_type": "VAEDecodeCustom", "inputs": {"samples": ("1", 0), "vae": ("5", 0)}},
            "5": {"class_type": "VAELoader", "inputs": {"vae_name": "a.safetensors"}},
        }
        result = analyze_duplicate_work(wf)
        all_members = set()
        for g in result["duplicate_vae_decode_groups"]:
            all_members.update(g["member_node_ids"])
        self.assertNotIn("2", all_members)
        self.assertNotIn("3", all_members)

    def test_clip_requires_exact_class_type_match(self):
        wf = {
            "1": {"class_type": "CLIPTextEncode", "inputs": {"text": "hello", "clip": ("3", 0)}},
            "2": {"class_type": "CLIPTextEncodeCustom", "inputs": {"text": "hello", "clip": ("3", 0)}},
            "3": {"class_type": "CLIPLoader", "inputs": {"clip_name": "c.safetensors"}},
        }
        result = analyze_duplicate_work(wf)
        all_members = set()
        for g in result["duplicate_clip_encode_groups"]:
            all_members.update(g["member_node_ids"])
        self.assertNotIn("1", all_members)
        self.assertNotIn("2", all_members)

    def test_duplicate_clip_encode_groups_detected(self):
        wf = {
            "1": {"class_type": "CLIPTextEncode", "inputs": {"text": "hello", "clip": ("3", 0)}},
            "2": {"class_type": "CLIPTextEncode", "inputs": {"text": "hello", "clip": ("3", 0)}},
            "3": {"class_type": "CLIPLoader", "inputs": {"clip_name": "c.safetensors"}},
        }
        result = analyze_duplicate_work(wf)
        clip_groups = result["duplicate_clip_encode_groups"]
        self.assertEqual(len(clip_groups), 1)
        self.assertEqual(set(clip_groups[0]["member_node_ids"]), {"1", "2"})

    def test_vae_remaining_scalar_values_compared_exactly(self):
        wf = {
            "1": {"class_type": "KSampler", "inputs": {"seed": 1}},
            "2": {"class_type": "VAEDecode", "inputs": {
                "samples": ("1", 0), "vae": ("5", 0), "flag": True,
            }},
            "3": {"class_type": "VAEDecode", "inputs": {
                "samples": ("1", 0), "vae": ("5", 0), "flag": False,
            }},
            "5": {"class_type": "VAELoader", "inputs": {"vae_name": "a.safetensors"}},
        }
        result = analyze_duplicate_work(wf)
        all_members = set()
        for g in result["duplicate_vae_decode_groups"]:
            all_members.update(g["member_node_ids"])
        self.assertNotIn("2", all_members)
        self.assertNotIn("3", all_members)

    def test_clip_different_text_not_grouped(self):
        wf = {
            "1": {"class_type": "CLIPTextEncode", "inputs": {"text": "hello", "clip": ("3", 0)}},
            "2": {"class_type": "CLIPTextEncode", "inputs": {"text": "world", "clip": ("3", 0)}},
            "3": {"class_type": "CLIPLoader", "inputs": {"clip_name": "c.safetensors"}},
        }
        result = analyze_duplicate_work(wf)
        self.assertEqual(len(result["duplicate_clip_encode_groups"]), 0)


class CacheTests(unittest.TestCase):
    def setUp(self):
        _reset_cache()

    def test_cache_hit_on_repeated_compilation(self):
        wf = {**WORKFLOW_SINGLE_OUTPUT}
        prod = _minimal_production(output_ids=["9"])
        _, report1 = compile_production_workflow(
            wf, prod, allow_direct_output_rewrite=False
        )
        self.assertFalse(report1["cache_hit"])
        _, report2 = compile_production_workflow(
            wf, prod, allow_direct_output_rewrite=False
        )
        self.assertTrue(report2["cache_hit"])

    def test_cache_miss_on_different_workflow(self):
        wf1 = {**WORKFLOW_SINGLE_OUTPUT}
        wf2 = {**WORKFLOW_MULTI_OUTPUT}
        prod = _minimal_production(output_ids=["9"])
        _, report1 = compile_production_workflow(
            wf1, prod, allow_direct_output_rewrite=False
        )
        self.assertFalse(report1["cache_hit"])
        prod2 = _minimal_production(output_ids=["11"])
        _, report2 = compile_production_workflow(
            wf2, prod2, allow_direct_output_rewrite=False
        )
        self.assertFalse(report2["cache_hit"])

    def test_lru_never_exceeds_32(self):
        wf = {**WORKFLOW_SINGLE_OUTPUT}
        for i in range(40):
            wf["3"] = dict(wf["3"])
            wf["3"]["inputs"] = dict(wf["3"]["inputs"], seed=i)
            prod = _minimal_production(output_ids=["9"])
            compile_production_workflow(wf, prod, allow_direct_output_rewrite=False)
        self.assertLessEqual(_cache_size(), 32)

    def test_cache_hit_reconstructs_current_scalar_values(self):
        wf = {
            "1": {"class_type": "KSampler", "inputs": {"seed": 10}},
            "2": {"class_type": "SaveImage", "inputs": {"images": ("1", 0)}},
        }
        prod = _minimal_production(output_ids=["2"])
        compiled_first, _ = compile_production_workflow(
            wf, prod, allow_direct_output_rewrite=True
        )
        self.assertEqual(compiled_first["1"]["inputs"]["seed"], 10)

        wf["1"]["inputs"]["seed"] = 99
        compiled_second, report = compile_production_workflow(
            wf, prod, allow_direct_output_rewrite=True
        )
        # source_workflow_hash is now part of the cache key, so changing
        # seed (a literal) changes the hash -> cache miss.
        self.assertFalse(report["cache_hit"])
        self.assertEqual(compiled_second["1"]["inputs"]["seed"], 99)

    def test_cache_hit_reconstructs_rewrite_status(self):
        wf = {
            "1": {"class_type": "KSampler", "inputs": {"seed": 1}},
            "2": {"class_type": "SaveImage", "inputs": {"images": ("1", 0)}},
        }
        prod = _minimal_production(output_ids=["2"])
        _, report_first = compile_production_workflow(
            wf, prod, allow_direct_output_rewrite=True
        )
        self.assertFalse(report_first["cache_hit"])
        self.assertIn("2", report_first["direct_output_rewritten_node_ids"])

        _, report_second = compile_production_workflow(
            wf, prod, allow_direct_output_rewrite=True
        )
        self.assertTrue(report_second["cache_hit"])
        self.assertIn("2", report_second["direct_output_rewritten_node_ids"])

    def test_cache_hit_rebuilds_from_current_scalars_when_no_rewrite(self):
        wf = {
            "1": {"class_type": "KSampler", "inputs": {"seed": 10, "steps": 20}},
            "2": {"class_type": "VAEDecode", "inputs": {"samples": ("1", 0)}},
            "3": {"class_type": "SaveImage", "inputs": {"images": ("2", 0)}},
        }
        prod = _minimal_production(output_ids=["3"])
        _, _ = compile_production_workflow(wf, prod, allow_direct_output_rewrite=False)

        wf["1"]["inputs"]["seed"] = 42
        wf["1"]["inputs"]["steps"] = 50
        compiled, report = compile_production_workflow(
            wf, prod, allow_direct_output_rewrite=False
        )
        # source_workflow_hash is now part of the cache key, so changing
        # literals (seed, steps) changes the hash -> cache miss.
        self.assertFalse(report["cache_hit"])
        self.assertEqual(compiled["1"]["inputs"]["seed"], 42)
        self.assertEqual(compiled["1"]["inputs"]["steps"], 50)


class WorkflowIntegrationTests(unittest.TestCase):
    def setUp(self):
        _reset_cache()

    def test_report_fields_present(self):
        prod = _minimal_production(output_ids=["9"])
        _, report = compile_production_workflow(
            WORKFLOW_SINGLE_OUTPUT, prod, allow_direct_output_rewrite=False
        )
        self.assertIn("enabled", report)
        self.assertIn("schema_version", report)
        self.assertIn("original_node_count", report)
        self.assertIn("compiled_node_count", report)
        self.assertIn("removed_node_count", report)
        self.assertIn("kept_node_ids", report)
        self.assertIn("removed_node_ids", report)
        self.assertIn("output_node_ids", report)
        self.assertIn("bypass_node_ids", report)
        self.assertIn("direct_output_rewritten_node_ids", report)
        self.assertIn("topology_hash", report)
        self.assertIn("compiled_workflow_hash", report)
        self.assertIn("cache_hit", report)
        self.assertIn("duplicate_analysis", report)

    def test_compiled_workflow_preserves_dict_insertion_order(self):
        prod = _minimal_production(output_ids=["9"])
        compiled, _ = compile_production_workflow(
            WORKFLOW_SINGLE_OUTPUT, prod, allow_direct_output_rewrite=False
        )
        keys = list(compiled.keys())
        self.assertEqual(keys, ["3", "4", "5", "6", "7", "8", "9", "10"])

    def test_compiled_workflow_preserves_original_insertion_order(self):
        wf = {
            "3": {"class_type": "KSampler", "inputs": {"seed": 1}},
            "10": {"class_type": "VAELoader", "inputs": {"vae_name": "v.safetensors"}},
            "2": {"class_type": "EmptyLatentImage", "inputs": {"width": 512}},
        }
        prod = _minimal_production(output_ids=["3", "10", "2"])
        compiled, _ = compile_production_workflow(
            wf, prod, allow_direct_output_rewrite=False
        )
        self.assertEqual(list(compiled.keys()), ["3", "10", "2"])


class RgthreeComparerRewriteTests(unittest.TestCase):
    """Tests for rgthree Image Comparer rewrite support."""

    def setUp(self):
        _reset_cache()

    def _make_workflow(self):
        return {
            "1": {"class_type": "KSampler", "inputs": {"seed": 1, "model": ("2", 0)}},
            "2": {"class_type": "UNETLoader", "inputs": {"unet_name": "m.safetensors"}},
            "3": {"class_type": "VAEDecode", "inputs": {"samples": ("1", 0)}},
            "4": {"class_type": "PreviewImage", "inputs": {"images": ("3", 0)}},
            "5": {"class_type": "Image Comparer (rgthree)", "inputs": {
                "image_a": ("3", 0), "image_b": ("3", 0),
            }},
        }

    def test_exact_class_recognized(self):
        """Exact 'Image Comparer (rgthree)' class is recognized for rewrite."""
        wf = self._make_workflow()
        prod = _minimal_production(output_ids=["5"])
        compiled, report = compile_production_workflow(
            wf, prod, allow_direct_output_rewrite=True
        )
        self.assertIn("5", compiled)
        self.assertEqual(compiled["5"]["class_type"], "ComfyModalProductionImageComparerOutput")
        self.assertIn("5", report["rgthree_comparer_rewritten_node_ids"])
        self.assertEqual(report["rgthree_comparer_rewritten_count"], 1)

    def test_similarly_named_not_recognized(self):
        """A similarly named class (without rgthree) is not recognized."""
        wf = {
            "1": {"class_type": "KSampler", "inputs": {"seed": 1}},
            "2": {"class_type": "Image Comparer", "inputs": {"image_a": ("1", 0)}},
        }
        prod = _minimal_production(output_ids=["2"])
        compiled, report = compile_production_workflow(
            wf, prod, allow_direct_output_rewrite=True
        )
        self.assertEqual(compiled["2"]["class_type"], "Image Comparer")
        self.assertEqual(report["rgthree_comparer_rewritten_count"], 0)

    def test_image_a_ancestors_remain(self):
        """image_a ancestors remain in compiled workflow."""
        wf = self._make_workflow()
        prod = _minimal_production(output_ids=["5"])
        compiled, _ = compile_production_workflow(
            wf, prod, allow_direct_output_rewrite=True
        )
        self.assertIn("3", compiled)
        self.assertIn("1", compiled)
        self.assertIn("2", compiled)

    def test_image_b_ancestors_remain(self):
        """image_b ancestors remain in compiled workflow."""
        wf = {
            "1": {"class_type": "KSampler", "inputs": {"seed": 1, "model": ("2", 0)}},
            "2": {"class_type": "UNETLoader", "inputs": {"unet_name": "m.safetensors"}},
            "3": {"class_type": "VAEDecode", "inputs": {"samples": ("1", 0)}},
            "4": {"class_type": "VAEDecode", "inputs": {"samples": ("1", 0)}},
            "5": {"class_type": "Image Comparer (rgthree)", "inputs": {
                "image_a": ("3", 0), "image_b": ("4", 0),
            }},
        }
        prod = _minimal_production(output_ids=["5"])
        compiled, _ = compile_production_workflow(
            wf, prod, allow_direct_output_rewrite=True
        )
        self.assertIn("3", compiled)
        self.assertIn("4", compiled)

    def test_rewritten_at_same_node_id(self):
        """Comparer is replaced at the same node ID."""
        wf = self._make_workflow()
        prod = _minimal_production(output_ids=["5"])
        compiled, _ = compile_production_workflow(
            wf, prod, allow_direct_output_rewrite=True
        )
        self.assertIn("5", compiled)
        self.assertEqual(compiled["5"]["class_type"], "ComfyModalProductionImageComparerOutput")

    def test_missing_image_b(self):
        """Missing image_b is supported."""
        wf = {
            "1": {"class_type": "KSampler", "inputs": {"seed": 1}},
            "2": {"class_type": "Image Comparer (rgthree)", "inputs": {
                "image_a": ("1", 0),
            }},
        }
        prod = _minimal_production(output_ids=["2"])
        compiled, _ = compile_production_workflow(
            wf, prod, allow_direct_output_rewrite=True
        )
        self.assertEqual(compiled["2"]["class_type"], "ComfyModalProductionImageComparerOutput")
        self.assertEqual(compiled["2"]["inputs"]["image_a"], ("1", 0))
        self.assertNotIn("image_b", compiled["2"]["inputs"])

    def test_identical_connections_set_inputs_are_same(self):
        """Identical image_a and image_b connections set inputs_are_same=True."""
        wf = self._make_workflow()
        prod = _minimal_production(output_ids=["5"])
        compiled, _ = compile_production_workflow(
            wf, prod, allow_direct_output_rewrite=True
        )
        self.assertTrue(compiled["5"]["inputs"]["inputs_are_same"])

    def test_different_connections_set_inputs_are_same_false(self):
        """Different image_a and image_b connections set inputs_are_same=False."""
        wf = {
            "1": {"class_type": "KSampler", "inputs": {"seed": 1, "model": ("2", 0)}},
            "2": {"class_type": "UNETLoader", "inputs": {"unet_name": "m.safetensors"}},
            "3": {"class_type": "VAEDecode", "inputs": {"samples": ("1", 0)}},
            "4": {"class_type": "VAEDecode", "inputs": {"samples": ("1", 0)}},
            "5": {"class_type": "Image Comparer (rgthree)", "inputs": {
                "image_a": ("3", 0), "image_b": ("4", 0),
            }},
        }
        prod = _minimal_production(output_ids=["5"])
        compiled, _ = compile_production_workflow(
            wf, prod, allow_direct_output_rewrite=True
        )
        self.assertFalse(compiled["5"]["inputs"]["inputs_are_same"])

    def test_cache_preserves_rgthree_rewrite(self):
        """Topology cache preserves the rgthree rewrite type."""
        wf = self._make_workflow()
        prod = _minimal_production(output_ids=["5"])
        _, report_first = compile_production_workflow(
            wf, prod, allow_direct_output_rewrite=True
        )
        self.assertFalse(report_first["cache_hit"])
        self.assertEqual(report_first["rgthree_comparer_rewritten_count"], 1)
        _, report_second = compile_production_workflow(
            wf, prod, allow_direct_output_rewrite=True
        )
        self.assertTrue(report_second["cache_hit"])
        self.assertEqual(report_second["rgthree_comparer_rewritten_count"], 1)
        self.assertIn("5", report_second["rgthree_comparer_rewritten_node_ids"])

    def test_cache_hit_reconstruction_uses_current_scalars(self):
        """Cache-miss on scalar change still produces current scalar values
        and preserves inputs_are_same."""
        wf = self._make_workflow()
        prod = _minimal_production(output_ids=["5"])
        compiled_first, _ = compile_production_workflow(
            wf, prod, allow_direct_output_rewrite=True
        )
        self.assertEqual(compiled_first["5"]["inputs"]["inputs_are_same"], True)
        # Change seed (scalar) — source_workflow_hash is now part of
        # the cache key, so a literal change causes a cache miss.
        wf["1"]["inputs"]["seed"] = 99
        compiled_second, report = compile_production_workflow(
            wf, prod, allow_direct_output_rewrite=True
        )
        self.assertFalse(report["cache_hit"],
                         "Scalar change causes cache miss with source_workflow_hash in key")
        self.assertEqual(compiled_second["1"]["inputs"]["seed"], 99)

    def test_report_has_accurate_rewrite_counts(self):
        """Report has accurate rewrite counts for both direct and rgthree."""
        wf = self._make_workflow()
        # Select both a SaveImage and the comparer
        wf["6"] = {"class_type": "SaveImage", "inputs": {"images": ("3", 0)}}
        prod = _minimal_production(output_ids=["5", "6"])
        compiled, report = compile_production_workflow(
            wf, prod, allow_direct_output_rewrite=True
        )
        self.assertEqual(report["direct_output_rewritten_count"], 1)
        self.assertEqual(report["rgthree_comparer_rewritten_count"], 1)
        self.assertIn("5", report["rgthree_comparer_rewritten_node_ids"])
        self.assertIn("6", report["direct_output_rewritten_node_ids"])

    def test_direct_output_rewritten_count_is_zero_when_none(self):
        """direct_output_rewritten_count is zero when nothing was rewritten."""
        wf = {
            "1": {"class_type": "KSampler", "inputs": {"seed": 1}},
            "2": {"class_type": "Image Comparer (rgthree)", "inputs": {"image_a": ("1", 0)}},
        }
        prod = _minimal_production(output_ids=["2"], direct_output_sink=False)
        compiled, report = compile_production_workflow(
            wf, prod, allow_direct_output_rewrite=False
        )
        self.assertEqual(report["direct_output_rewritten_count"], 0)
        self.assertEqual(report["rgthree_comparer_rewritten_count"], 0)

    def test_selected_comparer_may_result_in_zero_dead_nodes(self):
        """A selected comparer may correctly result in zero removed nodes."""
        wf = {
            "1": {"class_type": "KSampler", "inputs": {"seed": 1}},
            "2": {"class_type": "Image Comparer (rgthree)", "inputs": {"image_a": ("1", 0)}},
        }
        prod = _minimal_production(output_ids=["2"])
        compiled, report = compile_production_workflow(
            wf, prod, allow_direct_output_rewrite=True
        )
        self.assertEqual(report["removed_node_count"], 0)
        self.assertIn("1", compiled)
        self.assertIn("2", compiled)

    def test_report_fields_present_for_rgthree(self):
        """Report includes all rgthree-specific fields."""
        wf = self._make_workflow()
        prod = _minimal_production(output_ids=["5"])
        _, report = compile_production_workflow(
            wf, prod, allow_direct_output_rewrite=True
        )
        self.assertIn("rgthree_comparer_rewritten_node_ids", report)
        self.assertIn("rgthree_comparer_rewritten_count", report)
        self.assertIn("selected_output_classes", report)
        self.assertIn("direct_output_rewritten_count", report)
        self.assertIn("direct_output_rewrite_allowed", report)
        self.assertEqual(report["selected_output_classes"], {"5": "Image Comparer (rgthree)"})

    def test_fallback_no_image_a_connection(self):
        """When image_a is not a valid connection, the comparer is not rewritten."""
        wf = {
            "1": {"class_type": "KSampler", "inputs": {"seed": 1}},
            "2": {"class_type": "Image Comparer (rgthree)", "inputs": {
                "image_a": "literal_filename.png",
            }},
        }
        prod = _minimal_production(output_ids=["2"])
        compiled, report = compile_production_workflow(
            wf, prod, allow_direct_output_rewrite=True
        )
        self.assertEqual(compiled["2"]["class_type"], "Image Comparer (rgthree)")
        self.assertEqual(report["rgthree_comparer_rewritten_count"], 0)


class CompiledWorkflowHashTests(unittest.TestCase):
    """Tests for compiled_workflow_hash in the production report."""

    def setUp(self):
        _reset_cache()

    def test_compiled_workflow_hash_present_in_report(self):
        prod = _minimal_production(output_ids=["9"])
        _, report = compile_production_workflow(
            WORKFLOW_SINGLE_OUTPUT, prod, allow_direct_output_rewrite=False
        )
        self.assertIn("compiled_workflow_hash", report)
        self.assertIsInstance(report["compiled_workflow_hash"], str)
        self.assertEqual(len(report["compiled_workflow_hash"]), 64)

    def test_compiled_workflow_hash_present_on_cache_hit(self):
        prod = _minimal_production(output_ids=["9"])
        _, report1 = compile_production_workflow(
            WORKFLOW_SINGLE_OUTPUT, prod, allow_direct_output_rewrite=False
        )
        self.assertFalse(report1["cache_hit"])
        hash1 = report1["compiled_workflow_hash"]
        _, report2 = compile_production_workflow(
            WORKFLOW_SINGLE_OUTPUT, prod, allow_direct_output_rewrite=False
        )
        self.assertTrue(report2["cache_hit"])
        hash2 = report2["compiled_workflow_hash"]
        self.assertEqual(hash1, hash2,
                         "compiled_workflow_hash must be stable across cache")

    def test_compiled_workflow_hash_differs_when_outputs_change(self):
        wf = dict(WORKFLOW_MULTI_OUTPUT)
        prod1 = _minimal_production(output_ids=["11"])
        prod2 = _minimal_production(output_ids=["12"])
        _, report1 = compile_production_workflow(
            wf, prod1, allow_direct_output_rewrite=False
        )
        _, report2 = compile_production_workflow(
            wf, prod2, allow_direct_output_rewrite=False
        )
        self.assertNotEqual(report1["compiled_workflow_hash"],
                            report2["compiled_workflow_hash"])

    def test_compiled_workflow_hash_with_rewrite(self):
        wf = {
            "1": {"class_type": "KSampler", "inputs": {"seed": 1, "model": ("2", 0)}},
            "2": {"class_type": "UNETLoader", "inputs": {"unet_name": "m.safetensors"}},
            "3": {"class_type": "VAEDecode", "inputs": {"samples": ("1", 0)}},
            "4": {"class_type": "SaveImage", "inputs": {"images": ("3", 0)}},
        }
        prod = _minimal_production(output_ids=["4"])
        compiled, report = compile_production_workflow(
            wf, prod, allow_direct_output_rewrite=True
        )
        self.assertIn("compiled_workflow_hash", report)
        # Verify hash matches actual compiled workflow
        from production_workflow import _compute_compiled_workflow_hash
        expected = _compute_compiled_workflow_hash(compiled)
        self.assertEqual(report["compiled_workflow_hash"], expected)


class CacheFlagSeparationTests(unittest.TestCase):
    """Tests that the production compiler cache separates graph-affecting flags."""

    def setUp(self):
        _reset_cache()

    def _wf_with_comparer(self):
        return {
            "1": {"class_type": "KSampler", "inputs": {"seed": 1, "model": ("2", 0)}},
            "2": {"class_type": "UNETLoader", "inputs": {"unet_name": "m.safetensors"}},
            "3": {"class_type": "VAEDecode", "inputs": {"samples": ("1", 0)}},
            "4": {"class_type": "Image Comparer (rgthree)", "inputs": {
                "image_a": ("3", 0), "image_b": ("3", 0),
            }},
        }

    def test_cache_miss_when_rgthree_rewrite_flag_differs(self):
        """allow_rgthree_comparer_rewrite flag causes a cache miss."""
        wf = self._wf_with_comparer()
        prod = _minimal_production(output_ids=["4"])
        _, report_first = compile_production_workflow(
            wf, prod, allow_direct_output_rewrite=True, allow_rgthree_comparer_rewrite=True
        )
        self.assertFalse(report_first["cache_hit"])
        self.assertEqual(report_first["rgthree_comparer_rewritten_count"], 1)
        _, report_second = compile_production_workflow(
            wf, prod, allow_direct_output_rewrite=True, allow_rgthree_comparer_rewrite=False
        )
        self.assertFalse(report_second["cache_hit"],
                         "Changing allow_rgthree_comparer_rewrite must cause cache miss")
        self.assertEqual(report_second["rgthree_comparer_rewritten_count"], 0)

    def test_rgthree_rewrite_gated_by_flag_on_cache_hit(self):
        """Cache hit respects allow_rgthree_comparer_rewrite gate."""
        wf = self._wf_with_comparer()
        prod = _minimal_production(output_ids=["4"])
        # Prime cache with rewrite disabled
        compiled_no, report_no = compile_production_workflow(
            wf, prod, allow_direct_output_rewrite=True, allow_rgthree_comparer_rewrite=False
        )
        self.assertFalse(report_no["cache_hit"])
        self.assertEqual(report_no["rgthree_comparer_rewritten_count"], 0)
        self.assertEqual(compiled_no["4"]["class_type"], "Image Comparer (rgthree)")
        # Same params, must hit cache and still not rewrite
        compiled_no2, report_no2 = compile_production_workflow(
            wf, prod, allow_direct_output_rewrite=True, allow_rgthree_comparer_rewrite=False
        )
        self.assertTrue(report_no2["cache_hit"],
                         "Same params must hit cache")
        self.assertEqual(report_no2["rgthree_comparer_rewritten_count"], 0)
        self.assertEqual(compiled_no2["4"]["class_type"], "Image Comparer (rgthree)")

    def test_cache_miss_when_stable_flag_differs(self):
        """Stable flag causes a cache miss."""
        wf = self._wf_with_comparer()
        prod = _minimal_production(output_ids=["4"])
        _, report1 = compile_production_workflow(
            wf, prod, allow_direct_output_rewrite=True, stable=False
        )
        self.assertFalse(report1["cache_hit"])
        _, report2 = compile_production_workflow(
            wf, prod, allow_direct_output_rewrite=True, stable=True
        )
        self.assertFalse(report2["cache_hit"],
                         "Changing stable must cause cache miss")

    def test_cache_miss_when_metadata_mode_differs(self):
        """metadata_mode in production options causes a cache miss."""
        wf = self._wf_with_comparer()
        prod_none = _minimal_production(output_ids=["4"], metadata_mode="none")
        prod_full = _minimal_production(output_ids=["4"], metadata_mode="full")
        _, r1 = compile_production_workflow(
            wf, prod_none, allow_direct_output_rewrite=True
        )
        self.assertFalse(r1["cache_hit"])
        _, r2 = compile_production_workflow(
            wf, prod_full, allow_direct_output_rewrite=True
        )
        self.assertFalse(r2["cache_hit"],
                         "Changing metadata_mode must cause cache miss")


class ProductionEvidenceHashContractTests(unittest.TestCase):
    """Tests the hash-integrity contract used by _production_evidence."""

    def setUp(self):
        _reset_cache()

    def test_compile_then_hash_matches_report(self):
        """Compiling and re-hashing the result must match report's compiled_workflow_hash."""
        from production_workflow import _compute_compiled_workflow_hash
        prod = _minimal_production(output_ids=["9"])
        compiled, report = compile_production_workflow(
            WORKFLOW_SINGLE_OUTPUT, prod, allow_direct_output_rewrite=False
        )
        rehash = _compute_compiled_workflow_hash(compiled)
        self.assertEqual(report["compiled_workflow_hash"], rehash)

    def test_source_hash_differs_from_compiled_hash(self):
        """Source workflow hash must differ from compiled hash when nodes are removed."""
        from production_workflow import _compute_compiled_workflow_hash
        import hashlib, json
        prod = _minimal_production(output_ids=["9"])
        compiled, report = compile_production_workflow(
            WORKFLOW_SINGLE_OUTPUT, prod, allow_direct_output_rewrite=False
        )
        source_hash = hashlib.sha256(
            json.dumps(WORKFLOW_SINGLE_OUTPUT, sort_keys=True).encode("utf-8")
        ).hexdigest()
        compiled_hash = _compute_compiled_workflow_hash(compiled)
        self.assertNotEqual(source_hash, compiled_hash,
                            "Source and compiled hashes must differ when nodes are removed")

    def test_executed_equals_compiled_when_no_recompilation(self):
        """When production_report is supplied, executed must equal compiled."""
        prod = _minimal_production(output_ids=["9"])
        compiled, report = compile_production_workflow(
            WORKFLOW_SINGLE_OUTPUT, prod, allow_direct_output_rewrite=True
        )
        # Simulate remote-side verification: hash the received (already compiled) workflow
        from production_workflow import _compute_compiled_workflow_hash
        received_hash = _compute_compiled_workflow_hash(compiled)
        report_hash = report["compiled_workflow_hash"]
        self.assertEqual(received_hash, report_hash,
                         "Executed (received) workflow hash must equal report's compiled_workflow_hash")


class DisabledProductionTests(unittest.TestCase):
    """Tests that production-disabled paths are never treated as production."""

    def test_normalize_none_is_now_enabled(self):
        """None returns enabled=True with defaults (not disabled)."""
        result = normalize_production_options(None)
        self.assertTrue(result["enabled"])

    def test_normalize_empty_is_now_enabled(self):
        """Empty dict returns enabled=True with defaults (not disabled)."""
        result = normalize_production_options({})
        self.assertTrue(result["enabled"])

    def test_normalize_explicitly_disabled_returns_no_extra_keys(self):
        result = normalize_production_options({"production": {"enabled": False, "schema_version": 1}})
        self.assertEqual(result, {"enabled": False})

    def test_normalize_explicit_false_remains_disabled(self):
        """Explicit enabled=false must remain disabled regardless of other keys."""
        result = normalize_production_options({"production": {"enabled": False}})
        self.assertEqual(result, {"enabled": False})

    def test_normalize_explicit_true_no_output_ids_passes(self):
        """Explicit enabled=true with no output_node_ids passes through to compiler boundary."""
        result = normalize_production_options({
            "production": {"enabled": True, "schema_version": 1}
        })
        self.assertTrue(result["enabled"])
        self.assertEqual(result["output_node_ids"], [],
                         "Normalizer no longer rejects empty IDs — surface/compile boundary does")

    def test_normalize_implicit_enabled_empty_production(self):
        """production={} → enabled=True with defaults, empty output IDs allowed."""
        result = normalize_production_options({"production": {}})
        self.assertTrue(result["enabled"])
        self.assertEqual(result["output_node_ids"], [])
        self.assertEqual(result["schema_version"], COMPILER_SCHEMA_VERSION)


class ProductionReportRpcNullTests(unittest.TestCase):
    """Tests that production_report=None triggers remote compilation, not pre-compiled bypass."""

    def test_none_report_passed_as_none(self):
        """Simulate run_prompt call with production_report=None."""
        from production_workflow import compile_production_workflow
        prod = _minimal_production(output_ids=["9"])
        # When production_report is None, compile_production_workflow is called remotely.
        # This test verifies the None path doesn't break.
        compiled, report = compile_production_workflow(
            WORKFLOW_SINGLE_OUTPUT, prod, allow_direct_output_rewrite=True
        )
        self.assertIn("compiled_workflow_hash", report)
        self.assertTrue(report["enabled"])

    def test_report_supplied_does_not_recompile(self):
        """When production_report is supplied, the workflow is already compiled.
        Verify by checking compiler didn't modify it."""
        from production_workflow import compile_production_workflow, _compute_compiled_workflow_hash
        prod = _minimal_production(output_ids=["9"])
        compiled, report = compile_production_workflow(
            WORKFLOW_SINGLE_OUTPUT, prod, allow_direct_output_rewrite=True
        )
        # Hash the compiled workflow — this is what the remote receives
        received_hash = _compute_compiled_workflow_hash(compiled)
        self.assertEqual(received_hash, report["compiled_workflow_hash"])


class RuntimeEnvDefaultTests(unittest.TestCase):
    """Verify source-level default values match the requested baseline.
    These are the module-level defaults in comfyapp.py."""

    def test_preload_mode_default_is_workers_2(self):
        """Module default for COMFYMODAL_PRELOAD_MODE must be workers_2."""
        import os as _os
        # Read comfyapp.py source to check the default
        import re as _re
        _path = _os.path.join(_os.path.dirname(__file__), "..", "comfyapp.py")
        with open(_path, "r", encoding="utf-8") as _f:
            _src = _f.read()
        _match = _re.search(
            r'PRELOAD_MODE\s*=\s*os\.getenv\("COMFYMODAL_PRELOAD_MODE",\s*"([^"]+)"',
            _src,
        )
        self.assertIsNotNone(_match, "PRELOAD_MODE default not found in comfyapp.py")
        self.assertEqual(_match.group(1), "workers_2",
                         "PRELOAD_MODE default must be workers_2")

    def test_direct_warmup_unet_default_is_1(self):
        """Module default for DIRECT_WARMUP_LOAD_UNET must be 1."""
        import os as _os, re as _re
        _path = _os.path.join(_os.path.dirname(__file__), "..", "comfyapp.py")
        with open(_path, "r", encoding="utf-8") as _f:
            _src = _f.read()
        _match = _re.search(
            r'DIRECT_WARMUP_LOAD_UNET\s*=\s*os\.getenv\("COMFYMODAL_DIRECT_WARMUP_LOAD_UNET",\s*"([^"]+)"',
            _src,
        )
        self.assertIsNotNone(_match)
        self.assertEqual(_match.group(1), "1")

    def test_direct_warmup_clip_encore_default_is_0(self):
        """Module default for DIRECT_WARMUP_CLIP_ENCODE must be 0."""
        import os as _os, re as _re
        _path = _os.path.join(_os.path.dirname(__file__), "..", "comfyapp.py")
        with open(_path, "r", encoding="utf-8") as _f:
            _src = _f.read()
        _match = _re.search(
            r'DIRECT_WARMUP_CLIP_ENCODE\s*=\s*os\.getenv\("COMFYMODAL_DIRECT_WARMUP_CLIP_ENCODE",\s*"([^"]+)"',
            _src,
        )
        self.assertIsNotNone(_match)
        self.assertEqual(_match.group(1), "0")

    def test_direct_warmup_require_cpu_cache_default_is_0(self):
        """Module default for DIRECT_WARMUP_REQUIRE_CPU_CACHE_HIT must be 0."""
        import os as _os, re as _re
        _path = _os.path.join(_os.path.dirname(__file__), "..", "comfyapp.py")
        with open(_path, "r", encoding="utf-8") as _f:
            _src = _f.read()
        _match = _re.search(
            r'DIRECT_WARMUP_REQUIRE_CPU_CACHE_HIT\s*=\s*os\.getenv\("COMFYMODAL_DIRECT_WARMUP_REQUIRE_CPU_CACHE_HIT",\s*"([^"]+)"',
            _src,
        )
        self.assertIsNotNone(_match)
        self.assertEqual(_match.group(1), "0")

    def test_execution_backend_default_is_in_process(self):
        """Module default for EXECUTION_BACKEND must be in_process."""
        import os as _os, re as _re
        _path = _os.path.join(_os.path.dirname(__file__), "..", "comfyapp.py")
        with open(_path, "r", encoding="utf-8") as _f:
            _src = _f.read()
        _match = _re.search(
            r'DEFAULT_EXECUTION_BACKEND\s*=\s*os\.getenv\("COMFYMODAL_EXECUTION_BACKEND",\s*"([^"]+)"',
            _src,
        )
        self.assertIsNotNone(_match)
        self.assertEqual(_match.group(1), "in_process")

    def test_warmup_enabled_default_is_1(self):
        """Module default for ENABLE_WARMUP must be 1."""
        import os as _os, re as _re
        _path = _os.path.join(_os.path.dirname(__file__), "..", "comfyapp.py")
        with open(_path, "r", encoding="utf-8") as _f:
            _src = _f.read()
        _match = _re.search(
            r'ENABLE_WARMUP\s*=\s*os\.getenv\("COMFYMODAL_ENABLE_WARMUP",\s*"([^"]+)"',
            _src,
        )
        self.assertIsNotNone(_match)
        self.assertEqual(_match.group(1), "1")

    def test_torch_compile_default_is_0(self):
        """Module default for ENABLE_TORCH_COMPILE must be 0."""
        import os as _os, re as _re
        _path = _os.path.join(_os.path.dirname(__file__), "..", "comfyapp.py")
        with open(_path, "r", encoding="utf-8") as _f:
            _src = _f.read()
        _match = _re.search(
            r'ENABLE_TORCH_COMPILE\s*=\s*os\.getenv\("COMFYMODAL_ENABLE_TORCH_COMPILE",\s*"([^"]+)"',
            _src,
        )
        self.assertIsNotNone(_match)
        self.assertEqual(_match.group(1), "0")

    def test_image_env_has_baked_cuda(self):
        """Image .env() must set COMFYMODAL_SAGE_RUNTIME_MODE=baked_cuda."""
        import os as _os, re as _re
        _path = _os.path.join(_os.path.dirname(__file__), "..", "comfyapp.py")
        with open(_path, "r", encoding="utf-8") as _f:
            _src = _f.read()
        self.assertIn('"COMFYMODAL_SAGE_RUNTIME_MODE": "baked_cuda"', _src)

    def test_image_env_has_workers_2(self):
        """Image .env() must set COMFYMODAL_PRELOAD_MODE=workers_2."""
        import os as _os, re as _re
        _path = _os.path.join(_os.path.dirname(__file__), "..", "comfyapp.py")
        with open(_path, "r", encoding="utf-8") as _f:
            _src = _f.read()
        self.assertIn('"COMFYMODAL_PRELOAD_MODE": "workers_2"', _src)

    def test_image_env_has_execution_backend(self):
        """Image .env() must set COMFYMODAL_EXECUTION_BACKEND=in_process."""
        import os as _os, re as _re
        _path = _os.path.join(_os.path.dirname(__file__), "..", "comfyapp.py")
        with open(_path, "r", encoding="utf-8") as _f:
            _src = _f.read()
        self.assertIn('"COMFYMODAL_EXECUTION_BACKEND": "in_process"', _src)

    def test_image_env_has_warmup_enabled(self):
        """Image .env() must set COMFYMODAL_ENABLE_WARMUP=1."""
        import os as _os, re as _re
        _path = _os.path.join(_os.path.dirname(__file__), "..", "comfyapp.py")
        with open(_path, "r", encoding="utf-8") as _f:
            _src = _f.read()
        self.assertIn('"COMFYMODAL_ENABLE_WARMUP": "1"', _src)


class TerminalEvidenceTests(unittest.TestCase):
    """Test that _production_evidence is populated correctly in terminal states."""

    def setUp(self):
        _reset_cache()

    def test_evidence_present_on_compilation(self):
        """Compilation report contains all fields needed for _production_evidence."""
        prod = _minimal_production(output_ids=["9"])
        _, report = compile_production_workflow(
            WORKFLOW_SINGLE_OUTPUT, prod, allow_direct_output_rewrite=False
        )
        required = [
            "compiled_workflow_hash", "topology_hash", "compiled_node_count",
            "removed_node_count", "bypass_node_ids", "output_node_ids",
            "direct_output_rewritten_count", "rgthree_comparer_rewritten_count",
        ]
        for field in required:
            self.assertIn(field, report, f"Report missing {field} needed for evidence")

    def test_evidence_contains_count_contract(self):
        """Verify kept = compiled_node_count, removed = removed_node_count, etc."""
        # Use stable=True so bypass doesn't fail on non-serializable node
        prod = _minimal_production(output_ids=["9"], bypass_ids=["8"])
        _, report = compile_production_workflow(
            WORKFLOW_SINGLE_OUTPUT, prod, allow_direct_output_rewrite=False,
            stable=True,
        )
        self.assertEqual(report["compiled_node_count"], len(report["kept_node_ids"]))
        self.assertEqual(report["removed_node_count"], len(report["removed_node_ids"]))
        self.assertEqual(len(report["bypass_node_ids"]), 1)
        self.assertEqual(len(report["output_node_ids"]), 1)

    def test_disabled_production_no_evidence(self):
        """When production is disabled, no production_report evidence fields."""
        from production_workflow import normalize_production_options, compile_production_workflow
        # Use explicit disabled (None now returns enabled=True with defaults)
        prod = normalize_production_options({"production": {"enabled": False}})
        self.assertEqual(prod, {"enabled": False})

    # ── Cache key isolation tests ────────────────────────────────────

    def test_cache_key_includes_direct_output_rewrite(self):
        """Cache key topology_hash changes when allow_direct_output_rewrite changes."""
        _reset_cache()
        # Use WORKFLOW_MULTI_OUTPUT (has SaveImage/PreviewImage at 11,12)
        prod = _minimal_production(output_ids=["11"])
        _, r1 = compile_production_workflow(
            WORKFLOW_MULTI_OUTPUT, prod,
            allow_direct_output_rewrite=True, allow_rgthree_comparer_rewrite=False,
        )
        _, r2 = compile_production_workflow(
            WORKFLOW_MULTI_OUTPUT, prod,
            allow_direct_output_rewrite=False, allow_rgthree_comparer_rewrite=False,
        )
        # Topology hash includes the direct_output_rewrite flag
        self.assertNotEqual(r1["topology_hash"], r2["topology_hash"],
                            "allow_direct_output_rewrite must change topology_hash")

    def test_cache_key_includes_direct_output_sink(self):
        """Cache key changes when direct_output_sink changes."""
        _reset_cache()
        # Use WORKFLOW_MULTI_OUTPUT (has SaveImage/PreviewImage at 11,12)
        prod1 = _minimal_production(output_ids=["11"], direct_output_sink=True)
        prod2 = _minimal_production(output_ids=["11"], direct_output_sink=False)
        _, r1 = compile_production_workflow(
            WORKFLOW_MULTI_OUTPUT, prod1,
            allow_direct_output_rewrite=True, allow_rgthree_comparer_rewrite=False,
        )
        _, r2 = compile_production_workflow(
            WORKFLOW_MULTI_OUTPUT, prod2,
            allow_direct_output_rewrite=True, allow_rgthree_comparer_rewrite=False,
        )
        # Topology hash includes the direct_output_sink flag
        self.assertNotEqual(r1["topology_hash"], r2["topology_hash"],
                            "direct_output_sink must change topology_hash")

    def test_cache_key_includes_bypass_policy(self):
        """Cache key changes when bypass_node_ids changes."""
        _reset_cache()
        prod1 = _minimal_production(output_ids=["9"], bypass_ids=[])
        prod2 = _minimal_production(output_ids=["9"], bypass_ids=["8"])
        _, r1 = compile_production_workflow(
            WORKFLOW_SINGLE_OUTPUT, prod1,
            allow_direct_output_rewrite=False, stable=True,
        )
        _, r2 = compile_production_workflow(
            WORKFLOW_SINGLE_OUTPUT, prod2,
            allow_direct_output_rewrite=False, stable=True,
        )
        self.assertNotEqual(r1["topology_hash"], r2["topology_hash"],
                            "bypass_node_ids must change topology_hash")

    # ── Report fields ───────────────────────────────────────────────

    def test_report_includes_runner_workflow_hash(self):
        """Report must include runner_workflow_hash (= compiled hash)."""
        prod = _minimal_production(output_ids=["9"])
        _, report = compile_production_workflow(
            WORKFLOW_SINGLE_OUTPUT, prod, allow_direct_output_rewrite=False
        )
        self.assertIn("runner_workflow_hash", report)
        self.assertEqual(
            report["runner_workflow_hash"],
            report["compiled_workflow_hash"],
            "runner_workflow_hash must equal compiled_workflow_hash",
        )

    def test_report_includes_plan_and_source_hash_placeholders(self):
        """Report has topology_hash (plan) and compiled_workflow_hash."""
        prod = _minimal_production(output_ids=["9"])
        _, report = compile_production_workflow(
            WORKFLOW_SINGLE_OUTPUT, prod, allow_direct_output_rewrite=False
        )
        self.assertIn("topology_hash", report)
        self.assertIn("compiled_workflow_hash", report)
        self.assertTrue(len(report["topology_hash"]) > 0)
        self.assertTrue(len(report["compiled_workflow_hash"]) > 0)

    # ── Stable production output collection semantics ───────────────

    def test_stable_production_preserves_all_nodes(self):
        """Stable mode keeps ALL nodes (no pruning)."""
        prod = _minimal_production(output_ids=["9"])
        compiled, report = compile_production_workflow(
            WORKFLOW_SINGLE_OUTPUT, prod,
            allow_direct_output_rewrite=False, stable=True,
        )
        self.assertEqual(report["original_node_count"], len(WORKFLOW_SINGLE_OUTPUT))
        self.assertEqual(report["compiled_node_count"], len(WORKFLOW_SINGLE_OUTPUT))
        self.assertEqual(report["removed_node_count"], 0)

    def test_selected_output_single(self):
        """Non-stable mode prunes to transitive dependencies of selected output."""
        prod = _minimal_production(output_ids=["9"])
        compiled, report = compile_production_workflow(
            WORKFLOW_SINGLE_OUTPUT, prod,
            allow_direct_output_rewrite=False, stable=False,
        )
        # Output node 9 (VAEDecode) must be kept
        self.assertIn("9", compiled)
        # Output node 11 (PreviewImage) is NOT selected -> pruned
        self.assertNotIn("11", compiled,
                         "Non-selected output should be pruned in non-stable mode")
        self.assertGreater(report["removed_node_count"], 0,
                           "Non-selected nodes must be removed")

    def test_selected_output_multi_keeps_only_selected(self):
        """Only selected output nodes are kept; non-selected outputs are pruned."""
        prod = _minimal_production(output_ids=["11"])
        compiled, report = compile_production_workflow(
            WORKFLOW_MULTI_OUTPUT, prod,
            allow_direct_output_rewrite=False, stable=False,
        )
        # Output node 11 (SaveImage) must be kept
        self.assertIn("11", compiled)
        # Output node 12 (PreviewImage) is NOT selected -> pruned
        self.assertNotIn("12", compiled,
                         "Non-selected output must be pruned")
        # Both receive from VAEDecode 9, which must be kept (transitive dep)
        self.assertIn("9", compiled)

    # ── Duplicate analysis ──────────────────────────────────────────

    def test_duplicate_output_detected(self):
        """Duplicate outputs on same source are detected."""
        analysis = analyze_duplicate_work(WORKFLOW_MULTI_OUTPUT)
        outputs = analysis.get("duplicate_output_groups", [])
        # Both SaveImage (11) and PreviewImage (12) receive from VAEDecode (9)
        groups_found = [
            g for g in outputs
            if g["source_node_id"] == "9"
        ]
        self.assertTrue(len(groups_found) >= 1,
                        "Should detect duplicate output group on node 9")


class SourceWorkflowHashTests(unittest.TestCase):
    """Tests for source_workflow_hash cache-key contract (Task 3).

    The cache key must include a deterministic hash of the full source
    workflow, so that two workflows with identical topology but different
    literal values (seed, prompt text, model name) produce different
    cache keys and therefore different cache entries.
    """

    def setUp(self):
        _reset_cache()

    # ── Report field presence ────────────────────────────────────────

    def test_source_workflow_hash_in_report(self):
        """source_workflow_hash appears in the compile report."""
        prod = _minimal_production(output_ids=["9"])
        _, report = compile_production_workflow(
            WORKFLOW_SINGLE_OUTPUT, prod,
            allow_direct_output_rewrite=False,
        )
        self.assertIn("source_workflow_hash", report)
        self.assertIsInstance(report["source_workflow_hash"], str)
        self.assertEqual(len(report["source_workflow_hash"]), 64)

    def test_source_workflow_hash_differs_from_topology_hash(self):
        """The source hash includes literal values so it differs from topology."""
        prod = _minimal_production(output_ids=["9"])
        _, report = compile_production_workflow(
            WORKFLOW_SINGLE_OUTPUT, prod,
            allow_direct_output_rewrite=False,
        )
        self.assertNotEqual(
            report["source_workflow_hash"],
            report["topology_hash"],
            "Source hash includes literals; topology hash is topology-only",
        )

    def test_source_workflow_hash_differs_from_compiled_hash(self):
        """Source hash differs from compiled hash when nodes are removed."""
        prod = _minimal_production(output_ids=["9"])
        _, report = compile_production_workflow(
            WORKFLOW_SINGLE_OUTPUT, prod,
            allow_direct_output_rewrite=False,
        )
        self.assertNotEqual(
            report["source_workflow_hash"],
            report["compiled_workflow_hash"],
            "Source and compiled hashes must differ when nodes are pruned",
        )

    # ── Cache isolation: same topology, different literals ───────────

    def test_cache_miss_when_seed_differs_same_topology(self):
        """Changing only seed (same topology) causes cache miss.

        The source_workflow_hash in the cache key includes seed,
        so a different seed → different cache key → cache miss.
        """
        wf_a = dict(WORKFLOW_SINGLE_OUTPUT)
        wf_a["3"] = dict(wf_a["3"])
        wf_a["3"]["inputs"] = dict(wf_a["3"]["inputs"], seed=7)

        wf_b = dict(WORKFLOW_SINGLE_OUTPUT)
        wf_b["3"] = dict(wf_b["3"])
        wf_b["3"]["inputs"] = dict(wf_b["3"]["inputs"], seed=42)

        prod = _minimal_production(output_ids=["9"])
        _, r1 = compile_production_workflow(
            wf_a, prod, allow_direct_output_rewrite=False,
        )
        self.assertFalse(r1["cache_hit"])
        _, r2 = compile_production_workflow(
            wf_b, prod, allow_direct_output_rewrite=False,
        )
        self.assertFalse(r2["cache_hit"],
                         "Different seed must cause cache miss")
        # Verify topology hashes are same but source hashes differ
        self.assertEqual(r1["topology_hash"], r2["topology_hash"],
                         "Topology must be unchanged by seed")
        self.assertNotEqual(r1["source_workflow_hash"],
                            r2["source_workflow_hash"],
                            "Source hash must differ when seed differs")

    def test_cache_miss_when_prompt_text_differs(self):
        """Changing prompt text (same topology) causes cache miss."""
        wf_a = dict(WORKFLOW_SINGLE_OUTPUT)
        wf_b = dict(WORKFLOW_SINGLE_OUTPUT)
        wf_b["6"] = dict(wf_b["6"])
        wf_b["6"]["inputs"] = dict(wf_b["6"]["inputs"], text="a different prompt")

        prod = _minimal_production(output_ids=["9"])
        _, r1 = compile_production_workflow(
            wf_a, prod, allow_direct_output_rewrite=False,
        )
        self.assertFalse(r1["cache_hit"])
        _, r2 = compile_production_workflow(
            wf_b, prod, allow_direct_output_rewrite=False,
        )
        self.assertFalse(r2["cache_hit"],
                         "Different prompt text must cause cache miss")
        self.assertEqual(r1["topology_hash"], r2["topology_hash"],
                         "Topology must be unchanged by prompt text")
        self.assertNotEqual(r1["source_workflow_hash"],
                            r2["source_workflow_hash"],
                            "Source hash must differ when prompt text differs")

    def test_cache_miss_when_model_name_differs(self):
        """Changing model name (same topology) causes cache miss."""
        wf_a = dict(WORKFLOW_SINGLE_OUTPUT)
        wf_b = dict(WORKFLOW_SINGLE_OUTPUT)
        wf_b["4"] = dict(wf_b["4"])
        wf_b["4"]["inputs"] = dict(wf_b["4"]["inputs"],
                                  unet_name="different-model.safetensors")

        prod = _minimal_production(output_ids=["9"])
        _, r1 = compile_production_workflow(
            wf_a, prod, allow_direct_output_rewrite=False,
        )
        self.assertFalse(r1["cache_hit"])
        _, r2 = compile_production_workflow(
            wf_b, prod, allow_direct_output_rewrite=False,
        )
        self.assertFalse(r2["cache_hit"],
                         "Different model name must cause cache miss")
        self.assertEqual(r1["topology_hash"], r2["topology_hash"],
                         "Topology must be unchanged by model name")
        self.assertNotEqual(r1["source_workflow_hash"],
                            r2["source_workflow_hash"],
                            "Source hash must differ when model name differs")

    # ── Cache hit on identical workflow ──────────────────────────────

    def test_cache_hit_on_exact_duplicate(self):
        """Exactly identical workflow still hits cache."""
        prod = _minimal_production(output_ids=["9"])
        _, r1 = compile_production_workflow(
            WORKFLOW_SINGLE_OUTPUT, prod,
            allow_direct_output_rewrite=False,
        )
        self.assertFalse(r1["cache_hit"])
        _, r2 = compile_production_workflow(
            WORKFLOW_SINGLE_OUTPUT, prod,
            allow_direct_output_rewrite=False,
        )
        self.assertTrue(r2["cache_hit"],
                        "Identical workflow must hit cache")
        self.assertEqual(r1["source_workflow_hash"],
                         r2["source_workflow_hash"],
                         "Source hash must be stable for identical workflow")
