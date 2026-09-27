"""Tests for portability_risk (pure Phase-G6 Workflow portability risk engine).

Runs with plain ``python tests/test_portability_risk_engine.py`` and is also
unittest/pytest-discoverable. No network, no GPU, no filesystem writes, no
Modal, no live generation. All evidence is prepared in-memory.
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import portability_contract as c
import portability_risk as pr


# ── Shared fixtures ───────────────────────────────────────────────────────

CORE_CLASSES = frozenset(
    {
        "SaveImage",
        "CheckpointLoaderSimple",
        "CheckpointLoader",
        "UNETLoader",
        "CLIPLoader",
        "DualCLIPLoader",
        "VAELoader",
        "VAEDecode",
        "CLIPTextEncode",
        "KSampler",
        "EmptySD3LatentImage",
        "ConditioningZeroOut",
        "ModelSamplingAuraFlow",
        "PrimitiveFloat",
        "PrimitiveStringMultiline",
        "PairConditioningSetProperties",
        "ImageRotate",
        "EmptyImage",
        "LoadImage",
        "LoadMask",
        "LoadVideo",
        "LoadAudio",
        # G2 §4.1 verified core attribution (nodes_model_patch.py); the
        # registry snapshot merely failed to list it (G1 §8).
        "ModelPatchLoader",
    }
)

ANALYZED_AT = "2026-08-23T00:00:00+00:00"


def core_only_prompt():
    return {
        "1": {
            "class_type": "CheckpointLoaderSimple",
            "inputs": {"ckpt_name": "v1.safetensors"},
        },
        "2": {
            "class_type": "CLIPTextEncode",
            "inputs": {"text": "a cat", "clip": ["1", 0]},
        },
        "3": {
            "class_type": "SaveImage",
            "inputs": {"filename_prefix": "out", "images": ["2", 0]},
        },
    }


def model_row(filename, state="installed", digest=None, sources=(None,)):
    return {
        "key": "%s|%s" % ("checkpoint", filename),
        "role": "checkpoint",
        "filename": filename,
        "state": state,
        "hash": digest,
        "source_urls": [s for s in sources if s],
        "installed": state == "installed",
    }


def core_only_evidence(**overrides):
    prompt = overrides.pop("executable_prompt", core_only_prompt())
    fields = dict(
        version_id="wv_core0000000000000000000000000000000000000000000000000000",
        graph_hash=c.sha256_of_canonical(prompt),
        executable_prompt=prompt,
        api_prompt_json={"workflow": {}, "output": prompt},
        graph_json={"id": "g", "nodes": []},
        dependency_metadata={
            "model_stack": {"checkpoint": ["v1.safetensors"]},
            "node_classes": sorted(
                n["class_type"] for n in prompt.values()
            ),
        },
        model_evidence=[
            model_row("v1.safetensors", digest="a" * 64, sources=["https://example.test/v1"])
        ],
        custom_node_evidence=(),
        node_provenance={},
        core_classes=CORE_CLASSES,
        manifest_readiness={"ready": True, "missing": []},
    )
    fields.update(overrides)
    return pr.make_evidence(**fields)


def corpus_prompt():
    """Golden-like audited-corpus executable prompt (G1 §10 reconciled)."""
    return {
        "66": {"class_type": "UNETLoader", "inputs": {"unet_name": "z_image_turbo_bf16.safetensors"}},
        "62": {"class_type": "CLIPLoader", "inputs": {"clip_name": "qwen_3_4b.safetensors", "type": "lumina2"}},
        "1277": {"class_type": "VAELoader", "inputs": {"vae_name": "ae.safetensors"}},
        "151": {
            "class_type": "ModelPatchLoader",
            "inputs": {"name": "Z-Image-Turbo-Fun-Controlnet-Union-2.1-2602-8steps.safetensors"},
        },
        "10": {"class_type": "CLIPTextEncode", "inputs": {"text": "prompt", "clip": ["62", 0]}},
        "20": {"class_type": "ModelSamplingAuraFlow", "inputs": {"shift": 3.1, "model": ["66", 0]}},
        "30": {"class_type": "Image Comparer (rgthree)", "inputs": {"image_A": ["40", 0], "image_B": ["41", 0]}},
        "35": {"class_type": "CacheDiT_Model_Optimizer", "inputs": {"model": ["20", 0]}},
        "40": {"class_type": "VAEDecode", "inputs": {"samples": ["50", 0], "vae": ["1277", 0]}},
        "41": {"class_type": "VAEDecode", "inputs": {"samples": ["52", 0], "vae": ["1277", 0]}},
        "50": {"class_type": "ClownsharKSampler_Beta", "inputs": {"model": ["35", 0], "noise_seed": 123}},
        "52": {"class_type": "easy showAnything", "inputs": {"data": ["40", 0]}},
        "60": {"class_type": "ImpactIfNone", "inputs": {"source": ["50", 0]}},
        "99": {"class_type": "SaveImage", "inputs": {"filename_prefix": "z-image", "images": ["30", 0]}},
    }


def corpus_graph_json():
    """UI graph with subgraphs plus a Note carrying URL/path-like text."""
    return {
        "id": "g",
        "nodes": [
            {
                "id": 5,
                "type": "Note",
                "widgets_values": [
                    "Download weights from https://huggingface.co/example/z_image "
                    "or copy C:\\models\\z_image.safetensors into place."
                ],
            },
            {
                "id": 7,
                "type": "UNETLoader",
                "widgets_values": ["z_image_turbo_bf16.safetensors"],
            },
        ],
        "definitions": {"subgraphs": [{"id": "935:481"}, {"id": "1149:1146"}]},
    }


CORPUS_PROVENANCE = {
    "Image Comparer (rgthree)": {"quality": "declared", "repo": "rgthree-comfy"},
    "CacheDiT_Model_Optimizer": {"quality": "declared", "repo": "ComfyUI-CacheDiT"},
    "ClownsharKSampler_Beta": {"quality": "inferred", "repo": "RES4LYF"},
    "easy showAnything": {"quality": "declared", "repo": "comfyui-easy-use"},
    "ImpactIfNone": {"quality": "declared", "repo": "comfyui-impact-pack"},
}


def corpus_model_rows():
    return [
        model_row("z_image_turbo_bf16.safetensors"),
        model_row("qwen_3_4b.safetensors"),
        model_row("ae.safetensors"),
    ]


def corpus_evidence(**overrides):
    prompt = overrides.pop("executable_prompt", corpus_prompt())
    fields = dict(
        version_id="wv_8821af78d5c8408d",
        graph_hash=c.sha256_of_canonical(prompt),
        executable_prompt=prompt,
        api_prompt_json={"workflow": {}, "output": prompt},
        graph_json=overrides.pop("graph_json", corpus_graph_json()),
        dependency_metadata={
            "model_stack": {
                "unet": ["z_image_turbo_bf16.safetensors"],
                "clip": ["qwen_3_4b.safetensors"],
                "vae": ["ae.safetensors"],
            },
            "node_classes": sorted({n["class_type"] for n in prompt.values()}),
        },
        model_evidence=overrides.pop("model_evidence", corpus_model_rows()),
        custom_node_evidence=(),
        node_provenance=overrides.pop("node_provenance", dict(CORPUS_PROVENANCE)),
        core_classes=CORE_CLASSES,
        manifest_readiness={"ready": True, "missing": []},
    )
    fields.update(overrides)
    return pr.make_evidence(**fields)


ENV_HIGH_FACTS = {
    "torch_stack_pinned": False,
    "custom_node_sources_pinned": False,
    "plugin_worktree_clean": False,
    "local_core_patch_diverged": True,
    "model_hashes_pinned": False,
    "base_image_digest_pinned": False,
}


def codes(issues):
    return [i["code"] for i in issues]


# ── 1–4: summary levels + environment isolation ───────────────────────────


class SummaryRiskTests(unittest.TestCase):
    def test_01_core_only_portable_graph_low(self):
        result = pr.analyze_workflow_version(core_only_evidence(), analyzed_at=ANALYZED_AT)
        self.assertEqual(result["risk_level"], "low")
        self.assertEqual(result["issues"], [])
        self.assertTrue(result["signals"][c.SIGNAL_EXACT_ROUNDTRIP_PROVEN])
        self.assertTrue(result["signals"][c.SIGNAL_MODEL_HASH_PINNED])
        self.assertTrue(result["signals"][c.SIGNAL_MODEL_REF_BASENAME_ONLY])

    def test_02_current_audited_corpus_medium(self):
        result = pr.analyze_workflow_version(corpus_evidence(), analyzed_at=ANALYZED_AT)
        self.assertEqual(result["risk_level"], "medium")
        self.assertIn(c.ISSUE_CUSTOM_NODE_UNPINNED, codes(result["issues"]))
        self.assertIn(c.ISSUE_MODEL_HASH_UNPINNED, codes(result["issues"]))
        self.assertIn(c.ISSUE_MODEL_EXTRACTION_GAP, codes(result["issues"]))
        self.assertIn(c.ISSUE_SUBGRAPH_FRONTEND_REQUIREMENT, codes(result["issues"]))
        self.assertNotIn(c.ISSUE_LOCAL_PATH_REFERENCE, codes(result["issues"]))
        self.assertNotIn(c.ISSUE_EXTERNAL_ENDPOINT_REFERENCE, codes(result["issues"]))
        self.assertNotIn(c.ISSUE_REQUIRED_INPUT_ASSET, codes(result["issues"]))
        self.assertFalse(result["signals"][c.SIGNAL_HAS_ABSOLUTE_PATH])
        self.assertFalse(result["signals"][c.SIGNAL_HAS_EXTERNAL_ENDPOINT])
        self.assertFalse(result["signals"][c.SIGNAL_REQUIRES_INPUT_ASSET])
        self.assertTrue(result["signals"][c.SIGNAL_USES_SUBGRAPHS])
        self.assertTrue(result["signals"][c.SIGNAL_EXACT_ROUNDTRIP_PROVEN])
        self.assertEqual(result["signals"][c.SIGNAL_CUSTOM_NODE_COUNT], 5)
        self.assertEqual(result["signals"][c.SIGNAL_CUSTOM_REPO_COUNT], 5)

    def test_03_env_high_does_not_alter_corpus_medium(self):
        result = pr.analyze_workflow_version(corpus_evidence(), analyzed_at=ANALYZED_AT)
        env = pr.build_environment_result(ENV_HIGH_FACTS)
        report = pr.assemble_report(
            result, environment_result=env, analyzed_at=ANALYZED_AT
        )
        self.assertEqual(report["risk_level"], "medium")
        self.assertEqual(report["environment"]["risk_level"], "high")
        self.assertEqual(
            report["environment"]["source"], c.ENVIRONMENT_SOURCE_CURRENT_STUDIO
        )
        self.assertNotIn(
            c.SUBJECT_ENVIRONMENT, {i["subject"] for i in report["issues"]}
        )
        c.validate_report(report)

    def test_04_env_high_with_core_only_low_stays_low(self):
        result = pr.analyze_workflow_version(core_only_evidence(), analyzed_at=ANALYZED_AT)
        env = pr.build_environment_result(ENV_HIGH_FACTS)
        report = pr.assemble_report(
            result, environment_result=env, analyzed_at=ANALYZED_AT
        )
        self.assertEqual(report["risk_level"], "low")
        self.assertEqual(report["environment"]["risk_level"], "high")
        c.validate_report(report)


# ── 5–13: findings ────────────────────────────────────────────────────────


class FindingTests(unittest.TestCase):
    def test_05_unpinned_custom_node_medium(self):
        prompt = {
            "1": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": "v1.safetensors"}},
            "2": {"class_type": "SomeWidgetNode", "inputs": {"value": 1}},
            "3": {"class_type": "SaveImage", "inputs": {"images": ["2", 0]}},
        }
        evidence = core_only_evidence(
            executable_prompt=prompt,
            graph_hash=c.sha256_of_canonical(prompt),
            node_provenance={"SomeWidgetNode": {"quality": "declared", "repo": "some-pack"}},
        )
        result = pr.analyze_workflow_version(evidence, analyzed_at=ANALYZED_AT)
        self.assertEqual(result["risk_level"], "medium")
        self.assertIn(c.ISSUE_CUSTOM_NODE_UNPINNED, codes(result["issues"]))
        self.assertFalse(result["signals"][c.SIGNAL_CUSTOM_NODE_REVISION_PINNED])

    def test_06_model_hash_missing_medium(self):
        evidence = core_only_evidence(
            model_evidence=[model_row("v1.safetensors", digest=None)]
        )
        result = pr.analyze_workflow_version(evidence, analyzed_at=ANALYZED_AT)
        self.assertEqual(result["risk_level"], "medium")
        self.assertIn(c.ISSUE_MODEL_HASH_UNPINNED, codes(result["issues"]))
        self.assertFalse(result["signals"][c.SIGNAL_MODEL_HASH_PINNED])

    def test_07_model_extraction_gap_represented(self):
        result = pr.analyze_workflow_version(corpus_evidence(), analyzed_at=ANALYZED_AT)
        self.assertTrue(result["signals"][c.SIGNAL_MODEL_EXTRACTION_GAP])
        gap = next(i for i in result["issues"] if i["code"] == c.ISSUE_MODEL_EXTRACTION_GAP)
        self.assertIn("ModelPatchLoader", gap["message"])
        self.assertEqual(gap["severity"], "medium")

    def test_08_input_asset_requirement_represented(self):
        prompt = {
            "1": {"class_type": "LoadImage", "inputs": {"image": "example.png"}},
            "2": {"class_type": "SaveImage", "inputs": {"images": ["1", 0]}},
        }
        evidence = core_only_evidence(
            executable_prompt=prompt,
            graph_hash=c.sha256_of_canonical(prompt),
        )
        result = pr.analyze_workflow_version(evidence, analyzed_at=ANALYZED_AT)
        self.assertTrue(result["signals"][c.SIGNAL_REQUIRES_INPUT_ASSET])
        asset = next(i for i in result["issues"] if i["code"] == c.ISSUE_REQUIRED_INPUT_ASSET)
        self.assertEqual(asset["subject"], c.SUBJECT_ASSETS)
        self.assertEqual(asset["severity"], "medium")

    def test_09_absolute_path_global_finding_without_target_effects(self):
        prompt = {
            "1": {"class_type": "UNETLoader", "inputs": {"unet_name": r"C:\Users\parla\models\big.safetensors"}},
            "2": {"class_type": "SaveImage", "inputs": {"images": ["1", 0]}},
        }
        evidence = core_only_evidence(
            executable_prompt=prompt,
            graph_hash=c.sha256_of_canonical(prompt),
            model_evidence=[model_row(r"C:\Users\parla\models\big.safetensors")],
        )
        result = pr.analyze_workflow_version(evidence, analyzed_at=ANALYZED_AT)
        self.assertTrue(result["signals"][c.SIGNAL_HAS_ABSOLUTE_PATH])
        path_issue = next(i for i in result["issues"] if i["code"] == c.ISSUE_LOCAL_PATH_REFERENCE)
        self.assertEqual(path_issue["severity"], "medium")
        report = pr.assemble_report(result, analyzed_at=ANALYZED_AT)
        for tid in c.TARGET_IDS:
            self.assertNotEqual(
                report["targets"][tid]["risk_level"], "high",
                "G6 must not fabricate per-target consequences",
            )

    def test_09b_posix_and_unc_paths_detected_url_paths_not(self):
        prompt = {
            "1": {"class_type": "UNETLoader", "inputs": {"unet_name": "/mnt/data/models/big.safetensors"}},
            "2": {"class_type": "VAELoader", "inputs": {"vae_name": "\\\\nas\\share\\ae.safetensors"}},
            "3": {"class_type": "SaveImage", "inputs": {"images": ["1", 0]}},
        }
        evidence = core_only_evidence(
            executable_prompt=prompt,
            graph_hash=c.sha256_of_canonical(prompt),
            model_evidence=[
                model_row("/mnt/data/models/big.safetensors"),
                model_row("\\\\nas\\share\\ae.safetensors"),
            ],
        )
        result = pr.analyze_workflow_version(evidence, analyzed_at=ANALYZED_AT)
        self.assertTrue(result["signals"][c.SIGNAL_HAS_ABSOLUTE_PATH])
        self.assertFalse(result["signals"][c.SIGNAL_MODEL_REF_BASENAME_ONLY])

    def test_10_functional_external_endpoint_finding(self):
        prompt = {
            "1": {"class_type": "SomeFetcher", "inputs": {"url": "https://api.example.com/generate"}},
            "2": {"class_type": "SaveImage", "inputs": {"images": ["1", 0]}},
        }
        evidence = core_only_evidence(
            executable_prompt=prompt,
            graph_hash=c.sha256_of_canonical(prompt),
            node_provenance={"SomeFetcher": {"quality": "declared", "repo": "some-pack"}},
        )
        result = pr.analyze_workflow_version(evidence, analyzed_at=ANALYZED_AT)
        self.assertTrue(result["signals"][c.SIGNAL_HAS_EXTERNAL_ENDPOINT])
        ep = next(i for i in result["issues"] if i["code"] == c.ISSUE_EXTERNAL_ENDPOINT_REFERENCE)
        self.assertEqual(ep["subject"], c.SUBJECT_ENDPOINTS)

    def test_11_note_text_url_ignored(self):
        result = pr.analyze_workflow_version(corpus_evidence(), analyzed_at=ANALYZED_AT)
        self.assertFalse(result["signals"][c.SIGNAL_HAS_EXTERNAL_ENDPOINT])
        self.assertFalse(result["signals"][c.SIGNAL_HAS_ABSOLUTE_PATH])
        self.assertNotIn(c.ISSUE_EXTERNAL_ENDPOINT_REFERENCE, codes(result["issues"]))
        self.assertNotIn(c.ISSUE_LOCAL_PATH_REFERENCE, codes(result["issues"]))

    def test_12_subgraph_signal_not_universal_blocker(self):
        result = pr.analyze_workflow_version(corpus_evidence(), analyzed_at=ANALYZED_AT)
        self.assertTrue(result["signals"][c.SIGNAL_USES_SUBGRAPHS])
        sg = next(i for i in result["issues"] if i["code"] == c.ISSUE_SUBGRAPH_FRONTEND_REQUIREMENT)
        self.assertEqual(sg["severity"], "low")
        self.assertNotEqual(result["risk_level"], "high")
        core_plus_subgraph = core_only_evidence(graph_json=corpus_graph_json())
        res2 = pr.analyze_workflow_version(core_plus_subgraph, analyzed_at=ANALYZED_AT)
        self.assertEqual(res2["risk_level"], "low")

    def test_13_unresolved_required_node_blocker(self):
        prompt = {
            "1": {"class_type": "GhostNode", "inputs": {"x": 1}},
            "2": {"class_type": "SaveImage", "inputs": {"images": ["1", 0]}},
        }
        evidence = core_only_evidence(
            executable_prompt=prompt,
            graph_hash=c.sha256_of_canonical(prompt),
        )
        result = pr.analyze_workflow_version(evidence, analyzed_at=ANALYZED_AT)
        self.assertTrue(result["signals"][c.SIGNAL_HAS_UNRESOLVED_NODE_TYPE])
        self.assertEqual(result["signals"][c.SIGNAL_UNRESOLVED_NODE_COUNT], 1)
        un = next(i for i in result["issues"] if i["code"] == c.ISSUE_UNRESOLVED_NODE_TYPE)
        self.assertEqual(un["severity"], "high")
        self.assertEqual(result["risk_level"], "high")


# ── 14–17: manifest, UNKNOWN, resolver behavior ───────────────────────────


class PolicyTests(unittest.TestCase):
    def test_14_manifest_not_ready_behavior(self):
        evidence = core_only_evidence(
            manifest_readiness={
                "ready": False,
                "missing": ["models: v1.safetensors (missing hash)"],
            }
        )
        result = pr.analyze_workflow_version(evidence, analyzed_at=ANALYZED_AT)
        mr = next(i for i in result["issues"] if i["code"] == c.ISSUE_MANIFEST_NOT_READY)
        self.assertEqual(mr["severity"], "high")
        self.assertEqual(mr["subject"], c.SUBJECT_MANIFEST)
        self.assertEqual(result["risk_level"], "high")
        self.assertNotIn(c.ISSUE_DEPENDENCY_MISSING, codes(result["issues"]))

    def test_15_unknown_when_analysis_impossible(self):
        base = dict(version_id="wv_x", graph_hash="b" * 64)
        cases = [
            pr.make_evidence(**base),
            pr.make_evidence(
                version_id="wv_y",
                graph_hash="b" * 64,
                executable_prompt={"1": {"class_type": "SaveImage", "inputs": {}}},
                graph_json="not-a-dict",
            ),
            pr.make_evidence(
                version_id="wv_z",
                graph_hash="b" * 64,
                executable_prompt=core_only_prompt(),
                models_available=False,
            ),
        ]
        for evidence in cases:
            result = pr.analyze_workflow_version(evidence, analyzed_at=ANALYZED_AT)
            self.assertEqual(result["risk_level"], "unknown")
            self.assertEqual(codes(result["issues"]), [pr.ISSUE_ANALYSIS_UNAVAILABLE])
            self.assertEqual(result["signals"], {})
            report = pr.assemble_report(result, analyzed_at=ANALYZED_AT)
            c.validate_report(report)

    def test_16_wrong_revision_resolvable_dependency(self):
        evidence = core_only_evidence(
            model_evidence=[
                model_row("v1.safetensors", state="wrong_version", digest="a" * 64)
            ],
            custom_node_evidence=[
                {
                    "name": "some-pack",
                    "state": "wrong_revision",
                    "install_path": "",
                    "installed_commit": "aaa",
                    "required_revision": "bbb",
                    "repository_url": "https://github.com/example/some-pack",
                    "classes": ["SomeWidgetNode"],
                }
            ],
            node_provenance={"SomeWidgetNode": {"quality": "declared", "repo": "some-pack", "revision": "bbb"}},
        )
        prompt = core_only_prompt()
        prompt["2"] = {"class_type": "SomeWidgetNode", "inputs": {"value": 1}}
        evidence = pr.make_evidence(
            **{
                **{f: getattr(evidence, f) for f in pr.PortabilityEvidence.__dataclass_fields__},
                "executable_prompt": prompt,
                "graph_hash": c.sha256_of_canonical(prompt),
            }
        )
        result = pr.analyze_workflow_version(evidence, analyzed_at=ANALYZED_AT)
        wr = next(i for i in result["issues"] if i["code"] == c.ISSUE_DEPENDENCY_WRONG_REVISION)
        self.assertEqual(wr["severity"], "medium")
        self.assertEqual(result["risk_level"], "medium")

    def test_17_exact_provenance_lowers_risk_vs_unresolved(self):
        resolved = corpus_evidence(
            node_provenance={
                cls: {"quality": "exact", "repo": spec["repo"], "revision": "f" * 40}
                for cls, spec in CORPUS_PROVENANCE.items()
            },
            model_evidence=[
                model_row(fn, digest="e" * 64)
                for fn in (
                    "z_image_turbo_bf16.safetensors",
                    "qwen_3_4b.safetensors",
                    "ae.safetensors",
                    "Z-Image-Turbo-Fun-Controlnet-Union-2.1-2602-8steps.safetensors",
                )
            ],
        )
        good = pr.analyze_workflow_version(resolved, analyzed_at=ANALYZED_AT)
        self.assertEqual(good["risk_level"], "low")
        self.assertTrue(good["signals"][c.SIGNAL_CUSTOM_NODE_REVISION_PINNED])
        bad = pr.analyze_workflow_version(corpus_evidence(), analyzed_at=ANALYZED_AT)
        self.assertEqual(bad["risk_level"], "medium")
        ghost = corpus_evidence(
            node_provenance=dict(CORPUS_PROVENANCE),
            executable_prompt={
                **corpus_prompt(),
                "77": {"class_type": "MysteryNode", "inputs": {"q": 1}},
            },
        )
        ghost = pr.make_evidence(
            **{
                **{f: getattr(ghost, f) for f in pr.PortabilityEvidence.__dataclass_fields__},
                "graph_hash": c.sha256_of_canonical(ghost.executable_prompt),
            }
        )
        worst = pr.analyze_workflow_version(ghost, analyzed_at=ANALYZED_AT)
        self.assertEqual(worst["risk_level"], "high")


# ── 18–22: determinism, contract validation ───────────────────────────────


class DeterminismTests(unittest.TestCase):
    def test_18_deterministic_issue_ordering(self):
        result = pr.analyze_workflow_version(corpus_evidence(), analyzed_at=ANALYZED_AT)
        expected = c.sort_issues(result["issues"])
        self.assertEqual(result["issues"], expected)
        ranks = {"high": 3, "medium": 2, "low": 1}
        sevs = [ranks[i["severity"]] for i in result["issues"]]
        self.assertEqual(sevs, sorted(sevs, reverse=True))

    def test_19_exact_counts(self):
        result = pr.analyze_workflow_version(corpus_evidence(), analyzed_at=ANALYZED_AT)
        tally = {sev: 0 for sev in c.COUNT_KEYS}
        for issue in result["issues"]:
            tally[issue["severity"]] += 1
        self.assertEqual(result["counts"], tally)
        self.assertEqual(result["issue_count"], len(result["issues"]))
        report = pr.assemble_report(result, analyzed_at=ANALYZED_AT)
        c.validate_report(report)

    def test_20_repeat_byte_equivalent_except_analyzed_at(self):
        r1 = pr.build_workflow_report(corpus_evidence(), analyzed_at=ANALYZED_AT)
        r2 = pr.build_workflow_report(corpus_evidence(), analyzed_at=ANALYZED_AT)
        self.assertEqual(c.canonical_json(r1), c.canonical_json(r2))
        r3 = pr.build_workflow_report(
            corpus_evidence(), analyzed_at="2026-08-23T23:59:59+00:00"
        )
        strip = lambda rep: {k: v for k, v in rep.items() if k != "analyzed_at"}
        self.assertEqual(
            c.canonical_json(strip(r1)), c.canonical_json(strip(r3))
        )
        self.assertNotEqual(r1["analyzed_at"], r3["analyzed_at"])

    def test_21_environment_issue_codes(self):
        specs = [
            ({"torch_stack_pinned": False}, c.ENV_TORCH_STACK_UNPINNED, "high"),
            ({"custom_node_sources_pinned": False}, c.ENV_CUSTOM_NODE_SOURCE_UNPINNED, "high"),
            ({"plugin_worktree_clean": False}, c.ENV_PLUGIN_WORKTREE_DIRTY, "high"),
            ({"local_core_patch_diverged": True}, c.ENV_LOCAL_CORE_PATCH_DIVERGENCE, "high"),
            ({"model_hashes_pinned": False}, c.ENV_MODEL_HASH_UNPINNED, "medium"),
            ({"base_image_digest_pinned": False}, c.ENV_BASE_IMAGE_DIGEST_UNPINNED, "medium"),
        ]
        for facts, expected_code, expected_severity in specs:
            env = pr.build_environment_result(facts)
            self.assertEqual(codes(env["issues"]), [expected_code])
            self.assertEqual(env["issues"][0]["severity"], expected_severity)
            self.assertEqual(env["source"], c.ENVIRONMENT_SOURCE_CURRENT_STUDIO)
        mixed = pr.build_environment_result(
            {"torch_stack_pinned": False, "model_hashes_pinned": False}
        )
        self.assertEqual(mixed["risk_level"], "high")
        clean = pr.build_environment_result(
            {
                "torch_stack_pinned": True,
                "custom_node_sources_pinned": True,
                "plugin_worktree_clean": True,
                "local_core_patch_diverged": False,
                "model_hashes_pinned": True,
                "base_image_digest_pinned": True,
            }
        )
        self.assertEqual(clean["risk_level"], "low")
        self.assertEqual(clean["issues"], [])
        unknown = pr.build_environment_result(None)
        self.assertEqual(unknown["risk_level"], "unknown")
        fabricated = pr.build_environment_result({"torch_stack_pinned": None})
        self.assertEqual(fabricated["risk_level"], "unknown")

    def test_22_invalid_issue_result_rejected_by_contract_validation(self):
        result = pr.analyze_workflow_version(corpus_evidence(), analyzed_at=ANALYZED_AT)
        report = pr.assemble_report(result, analyzed_at=ANALYZED_AT)
        bad_counts = dict(report)
        bad_counts["counts"] = {**report["counts"], "high": 5}
        with self.assertRaises(c.PortabilityContractError):
            c.validate_report(bad_counts)
        bad_sev = dict(report)
        bad_sev["issues"] = [{**report["issues"][0], "severity": "unknown"}]
        with self.assertRaises(c.PortabilityContractError):
            c.validate_report(bad_sev)
        bad_subject = dict(report)
        bad_subject["issues"] = [{**report["issues"][0], "subject": "widgets"}]
        with self.assertRaises(c.PortabilityContractError):
            c.validate_report(bad_subject)
        with self.assertRaises(c.PortabilityContractError):
            pr.assemble_report(
                result,
                target_results={
                    "local": {"risk_level": "bogus", "issue_codes": [], "advice": []}
                },
                analyzed_at=ANALYZED_AT,
            )


# ── 23–24: adapter shape + purity ─────────────────────────────────────────


class AdapterAndPurityTests(unittest.TestCase):
    def _resolver_shape_rows(self):
        """Exact DependencyResolver.resolve_version output shapes."""
        models = [
            {
                "key": "checkpoint|v1.safetensors",
                "role": "checkpoint",
                "filename": "v1.safetensors",
                "state": "installed",
                "model_id": "m1",
                "folder": "checkpoints",
                "hash": None,
                "size": 123,
                "local_path": r"C:\secret\v1.safetensors",
                "source_urls": [],
                "installed": True,
            },
            {
                "key": "lora|style.safetensors",
                "role": "lora",
                "filename": "style.safetensors",
                "state": "missing",
                "model_id": None,
                "folder": "loras",
                "hash": None,
                "size": None,
                "local_path": None,
                "source_urls": ["https://civitai.example/style"],
                "installed": False,
            },
        ]
        nodes = [
            {
                "name": "ComfyUI core",
                "state": "installed",
                "install_path": "",
                "installed_commit": "",
                "required_revision": "",
                "repository_url": "",
                "classes": ["SaveImage"],
            },
            {
                "name": "ghost-pack",
                "state": "missing",
                "install_path": "",
                "installed_commit": "",
                "required_revision": "",
                "repository_url": "",
                "classes": ["GhostNode"],
            },
            {
                "name": "known-pack",
                "state": "missing",
                "install_path": "",
                "installed_commit": "",
                "required_revision": "",
                "repository_url": "https://github.com/example/known-pack",
                "classes": ["KnownButAbsentNode"],
            },
        ]
        return models, nodes

    def test_23_prepared_dependency_resolver_shape_accepted(self):
        models, nodes = self._resolver_shape_rows()
        prompt = {
            "1": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": "v1.safetensors"}},
            "2": {"class_type": "LoraLoader", "inputs": {"lora_name": "style.safetensors", "model": ["1", 0]}},
            "3": {"class_type": "GhostNode", "inputs": {"x": ["1", 0]}},
            "4": {"class_type": "KnownButAbsentNode", "inputs": {"y": ["1", 0]}},
            "5": {"class_type": "SaveImage", "inputs": {"images": ["3", 0]}},
        }
        version = {
            "version_id": "wv_adapter000000000000000000000000000000000000000",
            "graph_hash": c.sha256_of_canonical(prompt),
            "graph_json": {"id": "g", "nodes": []},
            "api_prompt_json": {"workflow": {}, "output": prompt},
            "executable_prompt": prompt,
            "dependency_metadata": {
                "model_stack": {"checkpoint": ["v1.safetensors"], "lora": ["style.safetensors"]},
                "node_classes": sorted({n["class_type"] for n in prompt.values()}),
            },
        }
        evidence = pr.evidence_from_version_record(
            version,
            model_rows=models,
            custom_node_rows=nodes,
            core_classes=CORE_CLASSES,
            manifest_readiness={"ready": True, "missing": []},
        )
        result = pr.analyze_workflow_version(evidence, analyzed_at=ANALYZED_AT)
        self.assertIn(c.ISSUE_UNRESOLVED_NODE_TYPE, codes(result["issues"]))
        un = next(i for i in result["issues"] if i["code"] == c.ISSUE_UNRESOLVED_NODE_TYPE)
        self.assertEqual(un["severity"], "high")
        self.assertIn("GhostNode", un["message"])
        dm = next(i for i in result["issues"] if i["code"] == c.ISSUE_DEPENDENCY_MISSING)
        self.assertEqual(dm["severity"], "medium")
        self.assertIn("style.safetensors", dm["message"])
        self.assertGreaterEqual(result["signals"][c.SIGNAL_CUSTOM_NODE_COUNT], 2)
        report = pr.assemble_report(result, analyzed_at=ANALYZED_AT)
        c.validate_report(report)

    def test_24_no_filesystem_or_network_access(self):
        from unittest import mock

        result = pr.analyze_workflow_version(corpus_evidence(), analyzed_at=ANALYZED_AT)
        env = pr.build_environment_result(ENV_HIGH_FACTS)
        boom_fs = AssertionError("filesystem access attempted")
        boom_net = AssertionError("network access attempted")
        with mock.patch("builtins.open", side_effect=boom_fs):
            with mock.patch("socket.socket", side_effect=boom_net):
                with mock.patch(
                    "urllib.request.urlopen", side_effect=boom_net
                ):
                    report = pr.assemble_report(
                        result, environment_result=env, analyzed_at=ANALYZED_AT
                    )
        c.validate_report(report)
        source = Path(pr.__file__).read_text(encoding="utf-8")
        for banned in (
            "import os",
            "import socket",
            "import urllib",
            "import requests",
            "import subprocess",
            "import pathlib",
            "open(",
            "requests.",
            "subprocess.",
        ):
            self.assertNotIn(banned, source)


# ── Extra coverage: new codes + signals ───────────────────────────────────


class NewCodeAndSignalTests(unittest.TestCase):
    def test_new_codes_stable_and_snake_case(self):
        for code in pr.NEW_ISSUE_CODES:
            self.assertRegex(code, r"^[a-z0-9]+(_[a-z0-9]+)*$")
        self.assertEqual(
            len(pr.ALL_ENGINE_ISSUE_CODES),
            len(set(pr.ALL_ENGINE_ISSUE_CODES)),
        )
        for code in c.FOUNDATIONAL_ISSUE_CODES:
            self.assertIn(code, pr.ALL_ENGINE_ISSUE_CODES)

    def test_credential_like_value_detected_high(self):
        prompt = {
            "1": {"class_type": "SomeFetcher", "inputs": {"api_token": "sup3rs3cret"}},
            "2": {"class_type": "SaveImage", "inputs": {"images": ["1", 0]}},
        }
        evidence = core_only_evidence(
            executable_prompt=prompt,
            graph_hash=c.sha256_of_canonical(prompt),
            node_provenance={"SomeFetcher": {"quality": "declared", "repo": "p"}},
        )
        result = pr.analyze_workflow_version(evidence, analyzed_at=ANALYZED_AT)
        cred = next(
            i for i in result["issues"]
            if i["code"] == c.ISSUE_CREDENTIAL_LIKE_VALUE_DETECTED
        )
        self.assertEqual(cred["severity"], "high")
        self.assertNotIn("sup3rs3cret", c.canonical_json(result))

    def test_env_bound_registry_leak_and_hash_mismatch_codes(self):
        prompt = core_only_prompt()
        evidence = core_only_evidence(
            env_bound_registry_leak=True,
            graph_hash="0" * 64,
        )
        result = pr.analyze_workflow_version(evidence, analyzed_at=ANALYZED_AT)
        self.assertIn(pr.ISSUE_ENV_BOUND_REGISTRY_LEAK, codes(result["issues"]))
        self.assertIn(pr.ISSUE_GRAPH_HASH_MISMATCH, codes(result["issues"]))
        self.assertFalse(result["signals"][c.SIGNAL_EXACT_ROUNDTRIP_PROVEN])


if __name__ == "__main__":
    unittest.main(verbosity=2)
