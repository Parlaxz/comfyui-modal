"""Unit tests for the ``--unique-prompt-suffix`` deterministic
conditioning-cache MISS vehicle in ``tools.benchmark_v2_direct``.

The exact-conditioning cache key (``clip_conditioning_cache
.build_exact_key_components``) includes BOTH the entry prompt text AND the
canonical ``workflow_hash`` (sha256 of the canonical JSON of the whole prompt
dict).  Appending a fresh token to every literal prompt-text source changes
both, guaranteeing a cache miss per run with no manual cache-state deletion
and no global cache-feature change.

These tests verify the mutation semantics (text sources only; loaders and
node-link inputs untouched), the no-op default, and the two hash axes the
miss relies on: ``prompt_sha256`` / ``plan.workflow_hash`` and the cache
``exact_key_digest``.
"""

from __future__ import annotations

import copy
import unittest
from typing import Any

from tools.benchmark_v2_direct import _apply_unique_prompt_suffix

# ── D1 registry-proof store isolation (never write the real shared store;
#    see tests/d1_store_isolation.py) ──────────────────────────────────
import sys as _d1_sys
from pathlib import Path as _d1_Path

if str(_d1_Path(__file__).resolve().parents[1]) not in _d1_sys.path:
    _d1_sys.path.insert(0, str(_d1_Path(__file__).resolve().parents[1]))
from tests.d1_store_isolation import isolate_module_store, restore_module_store  # noqa: E402


def setUpModule():
    isolate_module_store()


def tearDownModule():
    restore_module_store()

# ── Hermetic synthetic workflow mirroring the canonical benchmark shape:
#    PrimitiveStringMultiline (1497) -> JoinStrings (80) -> CLIPTextEncode
#    (67, text fed by a node LINK, not a literal), plus a second encode with
#    a LITERAL text string, loaders, and a non-text node. ────────────────
BASE_WORKFLOW: dict[str, Any] = {
    "3": {"class_type": "KSampler", "inputs": {
        "seed": 7, "steps": 20, "cfg": 3.5,
        "sampler_name": "euler", "scheduler": "normal", "denoise": 1,
    }},
    "4": {"class_type": "EmptyLatentImage", "inputs": {"width": 1024, "height": 1024}},
    "10": {"class_type": "UNETLoader", "inputs": {"unet_name": "flux-2-klein-9b-fp8.safetensors"}},
    "11": {"class_type": "CLIPLoader", "inputs": {"clip_name": "qwen_3_8b_fp8mixed.safetensors"}},
    "12": {"class_type": "VAELoader", "inputs": {"vae_name": "flux2-vae.safetensors"}},
    "67": {"class_type": "CLIPTextEncode", "inputs": {
        "clip": ["11", 0],
        "text": ["80", 0],  # node link — NOT a literal string
    }},
    "80": {"class_type": "JoinStrings", "inputs": {
        "delimiter": " ", "string1": ["1497", 0],
    }},
    "1497": {"class_type": "PrimitiveStringMultiline", "inputs": {
        "value": "A young female warrior with dark hair",
    }},
    "9": {"class_type": "CLIPTextEncode", "inputs": {
        "clip": ["11", 0],
        "text": "a literal positive prompt",
    }},
    "13": {"class_type": "ConditioningZeroOut", "inputs": {
        "conditioning": ["67", 0],
    }},
}


def _make_workflow() -> dict[str, Any]:
    return copy.deepcopy(BASE_WORKFLOW)


class UniquePromptSuffixMutationTests(unittest.TestCase):
    def test_appends_to_primitive_multiline_and_literal_encode_text(self):
        workflow = _make_workflow()
        modified = _apply_unique_prompt_suffix(workflow, "RUN-ABC")
        self.assertEqual(modified, 2)
        self.assertEqual(
            workflow["1497"]["inputs"]["value"],
            "A young female warrior with dark hair RUN-ABC",
        )
        self.assertEqual(
            workflow["9"]["inputs"]["text"],
            "a literal positive prompt RUN-ABC",
        )

    def test_does_not_touch_link_fed_encode_text(self):
        workflow = _make_workflow()
        _apply_unique_prompt_suffix(workflow, "RUN-ABC")
        # Wire-fed CLIPTextEncode text stays a node link (covered once at the
        # primitive source 1497, never double-suffixed at the encode).
        self.assertEqual(workflow["67"]["inputs"]["text"], ["80", 0])

    def test_does_not_touch_loader_or_non_text_nodes(self):
        workflow = _make_workflow()
        _apply_unique_prompt_suffix(workflow, "RUN-ABC")
        self.assertEqual(
            workflow["11"]["inputs"]["clip_name"], "qwen_3_8b_fp8mixed.safetensors"
        )
        self.assertEqual(
            workflow["10"]["inputs"]["unet_name"], "flux-2-klein-9b-fp8.safetensors"
        )
        self.assertEqual(
            workflow["12"]["inputs"]["vae_name"], "flux2-vae.safetensors"
        )
        self.assertEqual(workflow["3"]["inputs"]["seed"], 7)
        self.assertEqual(workflow["4"]["inputs"]["width"], 1024)
        # ConditioningZeroOut has no "text"/"value" literal to touch.
        self.assertEqual(workflow["13"]["inputs"]["conditioning"], ["67", 0])

    def test_other_text_encode_classes_covered_only_via_literal_text_input(self):
        # Design scope: any *TextEncode* class is covered ONLY through a
        # literal ``inputs["text"]``.  CLIPTextEncodeSDXL carries its prompt
        # in text_g/text_l (no ``inputs["text"]``), so it stays untouched —
        # its text is not part of the canonical workflow's key path.
        workflow = _make_workflow()
        workflow["99"] = {
            "class_type": "CLIPTextEncodeSDXL",
            "inputs": {
                "width": 1024, "height": 1024,
                "text_g": "global prompt", "text_l": "local prompt",
                "clip": ["11", 0],
            },
        }
        modified = _apply_unique_prompt_suffix(workflow, "RUN-XYZ")
        self.assertEqual(modified, 2)
        self.assertEqual(workflow["99"]["inputs"]["text_g"], "global prompt")
        self.assertEqual(workflow["99"]["inputs"]["text_l"], "local prompt")


class UniquePromptSuffixHashTests(unittest.TestCase):
    def test_prompt_sha256_changes_with_suffix(self):
        from workflow_metadata import prompt_sha256

        plain = _make_workflow()
        suffixed = _make_workflow()
        _apply_unique_prompt_suffix(suffixed, "RUN-0001")
        self.assertNotEqual(prompt_sha256(plain), prompt_sha256(suffixed))

    def test_build_execution_plan_workflow_hash_changes_with_suffix(self):
        # validate=False mirrors the benchmark runner (plan build with no live
        # node-registry validation); build_execution_plan runs in-process here.
        from canonical_execution import build_execution_plan

        plain = _make_workflow()
        suffixed = _make_workflow()
        _apply_unique_prompt_suffix(suffixed, "RUN-0001")
        plan_plain = build_execution_plan(plain, validate=False)
        plan_suffixed = build_execution_plan(suffixed, validate=False)
        self.assertNotEqual(plan_plain.workflow_hash, plan_suffixed.workflow_hash)


class UniquePromptSuffixCacheKeyTests(unittest.TestCase):
    @staticmethod
    def _entry_context(text: str, workflow_hash: str) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "format_version": 1,
            "clip_identity": "clip-identity-a",
            "clip_type": "SDXL",
            "loader_class": "CLIPLoader",
            "filenames": ["clip_a.safetensors"],
            "weight_dtype": "fp16",
            "compute_dtype": "fp16",
            "torch_version": "2.6.0",
            "torch_num_threads": 8,
            "model_generation": "sdxl",
            "tokenizer_identity": "tokenizer-a",
            "workflow_hash": workflow_hash,
            "deployment_hash": "deploy-a",
            "custom_node_generation": "gen-a",
            "production_options_hash": "prod-a",
            "entry_node_class": "CLIPTextEncode",
            "entry_role": "positive",
            "entry_prompt_input": "text",
            "entry_text": text,
            "entry_conditioning_inputs": {},
            "entry_adapter_chain": [],
            "entry_layer": "",
            "entry_skip": "",
        }

    def test_exact_key_digest_changes_with_entry_text(self):
        from comfymodal_runtime.clip_conditioning_cache import (
            build_exact_key_components,
            exact_key_digest,
        )

        ctx_a = self._entry_context("a warrior with dark hair", "hash-1")
        ctx_b = self._entry_context("a warrior with dark hair RUN-0001", "hash-1")
        digest_a = exact_key_digest(build_exact_key_components(ctx_a))
        digest_b = exact_key_digest(build_exact_key_components(ctx_b))
        self.assertNotEqual(digest_a, digest_b)

    def test_exact_key_digest_stable_for_identical_entry(self):
        from comfymodal_runtime.clip_conditioning_cache import (
            build_exact_key_components,
            exact_key_digest,
        )

        ctx_a = self._entry_context("same text", "hash-1")
        ctx_b = self._entry_context("same text", "hash-1")
        self.assertEqual(
            exact_key_digest(build_exact_key_components(ctx_a)),
            exact_key_digest(build_exact_key_components(ctx_b)),
        )

    def test_exact_key_digest_also_changes_with_workflow_hash(self):
        # Second independent miss axis: the suffixed prompt also changes the
        # canonical workflow_hash carried into the cache key.
        from comfymodal_runtime.clip_conditioning_cache import (
            build_exact_key_components,
            exact_key_digest,
        )

        ctx_a = self._entry_context("same text", "hash-1")
        ctx_b = self._entry_context("same text", "hash-2")
        self.assertNotEqual(
            exact_key_digest(build_exact_key_components(ctx_a)),
            exact_key_digest(build_exact_key_components(ctx_b)),
        )


class UniquePromptSuffixNoOpTests(unittest.TestCase):
    def test_empty_suffix_is_noop(self):
        workflow = _make_workflow()
        modified = _apply_unique_prompt_suffix(workflow, "")
        self.assertEqual(modified, 0)
        self.assertEqual(workflow, BASE_WORKFLOW)

    def test_none_suffix_is_noop(self):
        workflow = _make_workflow()
        modified = _apply_unique_prompt_suffix(workflow, None)  # type: ignore[arg-type]
        self.assertEqual(modified, 0)
        self.assertEqual(workflow, BASE_WORKFLOW)


class UniquePromptSuffixArgparseTests(unittest.TestCase):
    def test_unique_prompt_suffix_option_is_registered(self):
        # The argparse parser is built inside the `__main__` guard of the
        # benchmark module, so it is not reachable as an attribute at import
        # time.  Importing the module executes no heavy top-level code (the
        # guard defers argparse until `python tools/benchmark_v2_direct.py`),
        # so the lightest safe assertion is a static AST check that the
        # option is registered on the __main__ parser.
        import ast
        from pathlib import Path

        import tools.benchmark_v2_direct as benchmark_v2_direct

        tree = ast.parse(Path(benchmark_v2_direct.__file__).read_text(encoding="utf-8"))
        registered = False
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and getattr(node.func, "attr", None) == "add_argument"
                and node.args
                and isinstance(node.args[0], ast.Constant)
                and node.args[0].value == "--unique-prompt-suffix"
            ):
                registered = True
        self.assertTrue(
            registered,
            "--unique-prompt-suffix not registered on the __main__ argparse parser",
        )


if __name__ == "__main__":
    unittest.main()
