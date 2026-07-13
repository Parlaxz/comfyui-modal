import importlib.util
import sys
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
COMPILER_PATH = REPO_ROOT / "matrix_compiler.py"


def load_compiler():
    if not COMPILER_PATH.exists():
        raise AssertionError("matrix_compiler.py missing")
    spec = importlib.util.spec_from_file_location("matrix_compiler", COMPILER_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _callable(module, name):
    fn = getattr(module, name, None)
    if fn is None:
        raise AssertionError(f"matrix_compiler.py missing public function: {name}")
    return fn


def _lora_spec():
    """A spec with a single LoRA entry for strength validation tests."""
    spec = _minimal_spec()
    spec["loras"]["selections"] = [
        {"id": "L_a", "label": "A", "loras": [
            {"file": "a.safetensors", "model_strength": [0.7], "clip_strength": [0.7], "enabled": True},
        ], "enabled": True},
    ]
    return spec


def _minimal_spec():
    return {
        "experiment_id": "exp_1",
        "revision": 1,
        "workflows": [{
            "profile_id": "p1",
            "loader_target_group_id": "g_default",
            "main_triple": {"id": "main", "unet": "u1", "clip": "c1", "vae": "v1"},
            "subprofile_triples": [],
            "selected_triple_ids": ["main"],
            "lora_slots": [],
        }],
        "prompts": {
            "items": [
                {"id": "p_a", "label": "cat", "text": "a cat", "negative": None, "enabled": True},
                {"id": "p_b", "label": "dog", "text": "a dog", "negative": None, "enabled": True},
            ],
        },
        "images": {
            "mode": "cartesian",
            "items": [],
        },
        "loras": {
            "selections": [
                {"id": "L_no", "label": "No LoRA", "loras": [], "enabled": True},
            ],
        },
        "axes": {
            "shared": {
                "seed": {"mode": "list", "values": [1, 2]},
            },
            "per_workflow": {
                "p1": {
                    "steps": {"mode": "list", "values": [20]},
                },
            },
        },
    }


class CompileShapeTests(unittest.TestCase):
    def test_minimal_spec_produces_two_cells(self):
        c = load_compiler()
        spec = _minimal_spec()
        result = c.compile_experiment(spec)
        # 1 workflow * 1 triple * 1 LoRA * 2 prompts * 2 seeds * 1 step = 4
        self.assertEqual(len(result["cells"]), 4)

    def test_result_has_checkpoints(self):
        c = load_compiler()
        result = c.compile_experiment(_minimal_spec())
        self.assertEqual(len(result["checkpoints"]), 1)
        ck = result["checkpoints"][0]
        self.assertEqual(ck["profile_id"], "p1")
        self.assertEqual(ck["triple"]["unet"], "u1")

    def test_every_cell_has_cell_key(self):
        c = load_compiler()
        result = c.compile_experiment(_minimal_spec())
        for cell in result["cells"]:
            self.assertIn("cell_key", cell)
            self.assertEqual(len(cell["cell_key"]), 64)  # sha256 hex

    def test_sequences_are_sequential(self):
        c = load_compiler()
        result = c.compile_experiment(_minimal_spec())
        seqs = [cell["sequence"] for cell in result["cells"]]
        self.assertEqual(seqs, sorted(seqs))
        self.assertEqual(seqs, list(range(1, len(seqs) + 1)))


class StableKeysTests(unittest.TestCase):
    def test_same_input_same_keys(self):
        c = load_compiler()
        spec = _minimal_spec()
        r1 = c.compile_experiment(spec)
        r2 = c.compile_experiment(spec)
        keys1 = [cell["cell_key"] for cell in r1["cells"]]
        keys2 = [cell["cell_key"] for cell in r2["cells"]]
        self.assertEqual(keys1, keys2)

    def test_different_seed_different_key(self):
        c = load_compiler()
        spec = _minimal_spec()
        result = c.compile_experiment(spec)
        keys = [cell["cell_key"] for cell in result["cells"]]
        self.assertEqual(len(set(keys)), len(keys))

    def test_zero_value_preserved(self):
        c = load_compiler()
        spec = _minimal_spec()
        spec["axes"]["shared"]["guidance"] = {"mode": "list", "values": [0]}
        spec["axes"]["per_workflow"]["p1"]["guidance"] = {"mode": "list", "values": [0]}
        result = c.compile_experiment(spec)
        for cell in result["cells"]:
            self.assertEqual(cell["axis_values"]["guidance"], 0)


class CartesianImageTests(unittest.TestCase):
    def test_cartesian_prompt_image(self):
        c = load_compiler()
        spec = _minimal_spec()
        spec["prompts"]["items"] = [
            {"id": "p1", "label": "a", "text": "a", "negative": None, "enabled": True},
            {"id": "p2", "label": "b", "text": "b", "negative": None, "enabled": True},
        ]
        spec["images"]["items"] = [
            {"id": "i1", "content_hash": "h1", "enabled": True},
            {"id": "i2", "content_hash": "h2", "enabled": True},
            {"id": "i3", "content_hash": "h3", "enabled": True},
        ]
        result = c.compile_experiment(spec)
        # 2 prompts * 3 images = 6 prompt/image combinations
        # * 2 seeds * 1 step = 12
        self.assertEqual(len(result["cells"]), 12)


class PairedImageTests(unittest.TestCase):
    def test_paired_prompt_image_equal_lengths(self):
        c = load_compiler()
        spec = _minimal_spec()
        spec["prompts"]["items"] = [
            {"id": "p1", "label": "a", "text": "a", "negative": None, "enabled": True},
            {"id": "p2", "label": "b", "text": "b", "negative": None, "enabled": True},
        ]
        spec["images"]["mode"] = "paired"
        spec["images"]["items"] = [
            {"id": "i1", "content_hash": "h1", "enabled": True},
            {"id": "i2", "content_hash": "h2", "enabled": True},
        ]
        result = c.compile_experiment(spec)
        # 2 paired combos * 2 seeds * 1 step = 4
        self.assertEqual(len(result["cells"]), 4)

    def test_paired_unequal_lengths_skips_extras(self):
        c = load_compiler()
        spec = _minimal_spec()
        spec["prompts"]["items"] = [
            {"id": "p1", "label": "a", "text": "a", "negative": None, "enabled": True},
            {"id": "p2", "label": "b", "text": "b", "negative": None, "enabled": True},
            {"id": "p3", "label": "c", "text": "c", "negative": None, "enabled": True},
        ]
        spec["images"]["mode"] = "paired"
        spec["images"]["items"] = [
            {"id": "i1", "content_hash": "h1", "enabled": True},
        ]
        result = c.compile_experiment(spec)
        # only 1 paired combo * 2 seeds * 1 step = 2
        self.assertEqual(len(result["cells"]), 2)
        # duplicate_report should record the skipped count
        self.assertIn("warnings", result)
        self.assertTrue(any("uneven" in w.lower() or "skip" in w.lower() for w in result["warnings"]))


class T2INoImageTests(unittest.TestCase):
    def test_t2i_with_no_images_uses_no_image(self):
        c = load_compiler()
        spec = _minimal_spec()
        result = c.compile_experiment(spec)
        for cell in result["cells"]:
            self.assertEqual(cell["image_id"], "")


class LoRAGroupingTests(unittest.TestCase):
    def test_two_lora_selections_both_run(self):
        c = load_compiler()
        spec = _minimal_spec()
        spec["loras"]["selections"] = [
            {"id": "L_no", "label": "No LoRA", "loras": [], "enabled": True},
            {"id": "L_a", "label": "A", "loras": [
                {"file": "a.safetensors", "model_strength": [0.7], "clip_strength": [0.7], "enabled": True},
            ], "enabled": True},
        ]
        result = c.compile_experiment(spec)
        # 1 checkpoint * 2 LoRA selections * 2 prompts * 2 seeds = 8
        self.assertEqual(len(result["cells"]), 8)
        lora_ids = sorted({cell["lora_selection_id"] for cell in result["cells"]})
        self.assertEqual(lora_ids, ["L_a", "L_no"])

    def test_disabled_lora_selection_excluded(self):
        c = load_compiler()
        spec = _minimal_spec()
        spec["loras"]["selections"] = [
            {"id": "L_no", "label": "No LoRA", "loras": [], "enabled": True},
            {"id": "L_disabled", "label": "X", "loras": [
                {"file": "x.safetensors", "model_strength": [0.7], "clip_strength": [0.7], "enabled": True},
            ], "enabled": False},
        ]
        result = c.compile_experiment(spec)
        lora_ids = {cell["lora_selection_id"] for cell in result["cells"]}
        self.assertEqual(lora_ids, {"L_no"})

    def test_lora_strength_axes_are_inner(self):
        c = load_compiler()
        spec = _minimal_spec()
        spec["loras"]["selections"] = [
            {"id": "L_a", "label": "A", "loras": [
                {"file": "a.safetensors", "model_strength": [0.5, 1.0], "clip_strength": [0.5, 0.8], "enabled": True},
            ], "enabled": True},
        ]
        result = c.compile_experiment(spec)
        # 1 LoRA * 2 prompts * 4 strength combos * 2 seeds = 16
        self.assertEqual(len(result["cells"]), 16)


class CheckpointTests(unittest.TestCase):
    def test_one_checkpoint_per_triple(self):
        c = load_compiler()
        spec = _minimal_spec()
        spec["workflows"][0]["subprofile_triples"] = [
            {"id": "alt_bf16", "unet": "u_bf16", "clip": "c1", "vae": "v1", "enabled": True},
            {"id": "alt_fp8", "unet": "u_fp8", "clip": "c1", "vae": "v1", "enabled": True},
        ]
        spec["workflows"][0]["selected_triple_ids"] = ["main", "alt_bf16", "alt_fp8"]
        result = c.compile_experiment(spec)
        # 3 checkpoints, each 1 LoRA * 2 prompts * 2 seeds = 4
        self.assertEqual(len(result["checkpoints"]), 3)
        self.assertEqual(len(result["cells"]), 12)

    def test_disabled_subprofile_excluded(self):
        c = load_compiler()
        spec = _minimal_spec()
        spec["workflows"][0]["subprofile_triples"] = [
            {"id": "alt_disabled", "unet": "u_x", "clip": "c1", "vae": "v1", "enabled": False},
        ]
        spec["workflows"][0]["selected_triple_ids"] = ["main", "alt_disabled"]
        result = c.compile_experiment(spec)
        self.assertEqual(len(result["checkpoints"]), 1)


class CheapAxisOrderingTests(unittest.TestCase):
    def test_seed_is_innermost(self):
        c = load_compiler()
        spec = _minimal_spec()
        # Set cheap axes in non-default order to test that ordering
        # follows the fixed hierarchy (sampler > scheduler > steps >
        # guidance > denoise > lora > resolution > seed).
        spec["axes"]["shared"]["sampler"] = {"mode": "list", "values": ["euler", "dpm"]}
        spec["axes"]["per_workflow"]["p1"]["scheduler"] = {"mode": "list", "values": ["normal", "karras"]}
        result = c.compile_experiment(spec)
        samplers = [cell["axis_values"]["sampler"] for cell in result["cells"]]
        # Sampler must not alternate within a contiguous block; when it changes,
        # it may only change once per prompt block.
        transitions = 0
        for prev, cur in zip(samplers, samplers[1:]):
            if prev != cur:
                transitions += 1
        self.assertLessEqual(transitions, 3)
        self.assertEqual(samplers.count("euler"), 8)
        self.assertEqual(samplers.count("dpm"), 8)


class DuplicateDetectionTests(unittest.TestCase):
    def test_duplicate_cells_reported(self):
        c = load_compiler()
        spec = _minimal_spec()
        # Force duplicates: only one prompt, one image, one seed.
        spec["axes"]["shared"]["seed"] = {"mode": "list", "values": [42]}
        result = c.compile_experiment(spec)
        # With 1 prompt * 1 seed, there are 2 cells (the two different prompts from _minimal_spec)
        # but they have different keys. Make them collide by setting same text:
        spec["prompts"]["items"] = [
            {"id": "p_a", "label": "a", "text": "same", "negative": None, "enabled": True},
            {"id": "p_b", "label": "b", "text": "same", "negative": None, "enabled": True},
        ]
        result = c.compile_experiment(spec)
        # 2 cells with the same canonical key
        self.assertEqual(len(result["cells"]), 2)
        self.assertEqual(result["cells"][0]["cell_key"], result["cells"][1]["cell_key"])
        # duplicate_report should record it
        self.assertIn("duplicate_count", result)
        self.assertEqual(result["duplicate_count"], 1)


class ValidationTests(unittest.TestCase):
    def test_missing_workflows_raises(self):
        c = load_compiler()
        with self.assertRaises(c.CompilationError):
            c.compile_experiment({"experiment_id": "x"})

    def test_invalid_paired_skips_warning(self):
        c = load_compiler()
        spec = _minimal_spec()
        spec["images"]["mode"] = "paired"
        spec["images"]["items"] = [
            {"id": "i1", "content_hash": "h1", "enabled": True},
            {"id": "i2", "content_hash": "h2", "enabled": True},
            {"id": "i3", "content_hash": "h3", "enabled": True},
        ]
        # No prompt/image to pair with — should still produce 0 cells cleanly with a warning
        spec["prompts"]["items"] = []
        result = c.compile_experiment(spec)
        self.assertEqual(len(result["cells"]), 0)


class NegativePromptSemanticsTests(unittest.TestCase):
    """Shared negative prompt semantics must be correct everywhere:
    per-item negative → shared_negative → WORKFLOW_OWNED.
    Explicit empty string must clear the workflow negative field."""

    def test_per_item_negative_applies(self):
        c = load_compiler()
        spec = _minimal_spec()
        spec["prompts"]["items"] = [
            {"id": "p_a", "label": "cat", "text": "a cat", "negative": "bad cat", "enabled": True},
        ]
        result = c.compile_experiment(spec)
        for cell in result["cells"]:
            self.assertEqual(cell["negative_prompt"], "bad cat")

    def test_per_item_empty_string_clears_workflow(self):
        """Explicit empty string must clear the workflow negative field."""
        c = load_compiler()
        spec = _minimal_spec()
        spec["prompts"]["items"] = [
            {"id": "p_a", "label": "cat", "text": "a cat", "negative": "", "enabled": True},
        ]
        result = c.compile_experiment(spec)
        for cell in result["cells"]:
            self.assertEqual(cell["negative_prompt"], "")

    def test_shared_negative_applies_when_per_item_missing(self):
        """When per-item negative is not set, shared_negative should apply."""
        c = load_compiler()
        spec = _minimal_spec()
        spec["prompts"]["shared_negative"] = "shared bad"
        # Remove per-item negative
        for item in spec["prompts"]["items"]:
            del item["negative"]
        result = c.compile_experiment(spec)
        for cell in result["cells"]:
            self.assertEqual(cell["negative_prompt"], "shared bad")

    def test_shared_negative_fallback_when_per_item_is_none(self):
        """When per-item negative is None, fallback to shared_negative."""
        c = load_compiler()
        spec = _minimal_spec()
        spec["prompts"]["shared_negative"] = "fallback bad"
        spec["prompts"]["items"] = [
            {"id": "p_a", "label": "cat", "text": "a cat", "negative": None, "enabled": True},
        ]
        result = c.compile_experiment(spec)
        for cell in result["cells"]:
            self.assertEqual(cell["negative_prompt"], "fallback bad")

    def test_workflow_owned_when_both_missing(self):
        """When neither per-item negative nor shared_negative is set,
        the cell should carry WORKFLOW_OWNED."""
        c = load_compiler()
        spec = _minimal_spec()
        # Ensure no shared_negative
        spec["prompts"].pop("shared_negative", None)
        # Remove per-item negative
        for item in spec["prompts"]["items"]:
            del item["negative"]
        result = c.compile_experiment(spec)
        for cell in result["cells"]:
            self.assertTrue(c.is_workflow_owned(cell["negative_prompt"]))

    def test_workflow_owned_when_negative_is_none_no_shared(self):
        """When per-item negative is None and no shared_negative,
        cell carries WORKFLOW_OWNED."""
        c = load_compiler()
        spec = _minimal_spec()
        spec["prompts"].pop("shared_negative", None)
        spec["prompts"]["items"] = [
            {"id": "p_a", "label": "cat", "text": "a cat", "negative": None, "enabled": True},
        ]
        result = c.compile_experiment(spec)
        for cell in result["cells"]:
            self.assertTrue(c.is_workflow_owned(cell["negative_prompt"]))

    def test_shared_negative_empty_string_clears_workflow(self):
        """Explicit empty string as shared_negative also clears workflow."""
        c = load_compiler()
        spec = _minimal_spec()
        spec["prompts"]["shared_negative"] = ""
        for item in spec["prompts"]["items"]:
            del item["negative"]
        result = c.compile_experiment(spec)
        for cell in result["cells"]:
            self.assertEqual(cell["negative_prompt"], "")

    def test_per_item_override_overrides_shared(self):
        """Per-item negative must take priority over shared_negative."""
        c = load_compiler()
        spec = _minimal_spec()
        spec["prompts"]["shared_negative"] = "shared bad"
        spec["prompts"]["items"] = [
            {"id": "p_a", "label": "cat", "text": "a cat", "negative": "per item wins", "enabled": True},
        ]
        result = c.compile_experiment(spec)
        for cell in result["cells"]:
            self.assertEqual(cell["negative_prompt"], "per item wins")


def _experiment_spec():
    """A richer spec with multiple checkpoints, loras, and axes.
    Copied from test_integration_acceptance.py to avoid cross-module import."""
    return {
        "experiment_id": "exp_int",
        "revision": 1,
        "workflows": [{
            "profile_id": "p1",
            "loader_target_group_id": "g_default",
            "main_triple": {"id": "main", "unet": "u1", "clip": "c1", "vae": "v1"},
            "subprofile_triples": [
                {"id": "alt", "unet": "u2", "clip": "c1", "vae": "v1", "enabled": True},
            ],
            "selected_triple_ids": ["main", "alt"],
            "lora_slots": [],
        }],
        "prompts": {"items": [
            {"id": "p_a", "label": "a", "text": "a", "negative": None, "enabled": True},
            {"id": "p_b", "label": "b", "text": "b", "negative": None, "enabled": True},
        ]},
        "images": {"mode": "cartesian", "items": []},
        "loras": {"selections": [
            {"id": "L_no", "label": "No LoRA", "loras": [], "enabled": True},
            {"id": "L_a", "label": "A", "loras": [
                {"file": "a.safetensors", "model_strength": [0.7], "clip_strength": [0.7], "enabled": True},
            ], "enabled": True},
        ]},
        "axes": {
            "shared": {"seed": {"mode": "list", "values": [1, 2]},
                       "guidance": {"mode": "list", "values": [3.5, 0.0]}},
            "per_workflow": {"p1": {"steps": {"mode": "list", "values": [20]}}},
        },
    }


class WorkflowOwnedJsonTests(unittest.TestCase):
    """WORKFLOW_OWNED sentinel must be JSON-serializable."""

    def test_workflow_owned_serializes_to_json(self):
        """WORKFLOW_OWNED must survive json.dumps/json.loads round-trip."""
        compiler = load_compiler()
        spec = _experiment_spec()
        compilation = compiler.compile_experiment(spec)
        # The compilation must serialize to JSON without error
        import json
        serialized = json.dumps(compilation, ensure_ascii=False, sort_keys=True)
        restored = json.loads(serialized)
        # All cell axis_values containing WORKFLOW_OWNED should
        # survive the round-trip as the string "__COMFYMODAL_WORKFLOW_OWNED__"
        found_at_least_one = False
        for cell in restored["cells"]:
            av = cell.get("axis_values", {})
            for val in av.values():
                if val == compiler.WORKFLOW_OWNED:
                    found_at_least_one = True
                    break
        self.assertTrue(
            found_at_least_one,
            "Expected at least one axis value to be the WORKFLOW_OWNED sentinel "
            "after JSON round-trip — suggest adding axes without spec values",
        )

    def test_is_workflow_owned_after_roundtrip(self):
        """is_workflow_owned must recognise the sentinel after JSON round-trip."""
        compiler = load_compiler()
        spec = _experiment_spec()
        compilation = compiler.compile_experiment(spec)
        import json
        serialized = json.dumps(compilation, ensure_ascii=False, sort_keys=True)
        restored = json.loads(serialized)
        for cell in restored["cells"]:
            av = cell.get("axis_values", {})
            for val in av.values():
                if val == compiler.WORKFLOW_OWNED:
                    self.assertTrue(compiler.is_workflow_owned(val))


# ── D1: Empty LoRA strength validation ────────────────────────────────────

class EmptyLoraStrengthValidationTests(unittest.TestCase):
    """D1: Compiler raises CompilationError (not generic ValueError)
    for empty LoRA strength lists."""

    def _make_spec(self, model_strength, clip_strength):
        c = load_compiler()
        spec = _minimal_spec()
        spec["loras"]["selections"] = [
            {"id": "L_a", "label": "A", "loras": [
                {"file": "a.safetensors",
                 "model_strength": model_strength,
                 "clip_strength": clip_strength,
                 "enabled": True},
            ], "enabled": True},
        ]
        return c, spec

    def test_both_empty_raises_compilation_error(self):
        """model_strength=[] AND clip_strength=[] raises CompilationError."""
        c, spec = self._make_spec([], [])
        with self.assertRaises(c.CompilationError) as ctx:
            c.compile_experiment(spec)
        self.assertIn("strength", str(ctx.exception).lower())

    def test_empty_model_with_clip_raises_compilation_error(self):
        """model_strength=[] AND clip_strength=[0.5] raises CompilationError."""
        c, spec = self._make_spec([], [0.5])
        with self.assertRaises(c.CompilationError) as ctx:
            c.compile_experiment(spec)
        self.assertIn("strength", str(ctx.exception).lower())

    def test_empty_clip_with_model_raises_compilation_error(self):
        """model_strength=[0.7] AND clip_strength=[] raises CompilationError."""
        c, spec = self._make_spec([0.7], [])
        with self.assertRaises(c.CompilationError) as ctx:
            c.compile_experiment(spec)
        self.assertIn("strength", str(ctx.exception).lower())

    def test_both_zero_is_valid(self):
        """Both model_strength=[0] and clip_strength=[0] must compile successfully."""
        c, spec = self._make_spec([0], [0])
        result = c.compile_experiment(spec)
        self.assertEqual(len(result["cells"]), 4)  # 2 prompts * 2 seeds
        for cell in result["cells"]:
            ax = cell["axis_values"]
            self.assertEqual(ax["lora_model_strengths"], [0.0])
            self.assertEqual(ax["lora_clip_strengths"], [0.0])

    def test_multi_lora_cartesian_strength_still_works(self):
        """Multi-LoRA Cartesian product with explicit strengths still works."""
        c = load_compiler()
        spec = _minimal_spec()
        spec["loras"]["selections"] = [
            {"id": "L_multi", "label": "Multi", "loras": [
                {"file": "a.safetensors", "model_strength": [0.5, 1.0],
                 "clip_strength": [0.5, 0.8], "enabled": True},
                {"file": "b.safetensors", "model_strength": [0.3],
                 "clip_strength": [0.3], "enabled": True},
            ], "enabled": True},
        ]
        result = c.compile_experiment(spec)
        # 2 LoRAs: first has 4 strength combos (2x2), second has 1 (1x1)
        # Cartesian across LoRAs: 4*1 = 4 strength combos
        # * 2 prompts * 2 seeds = 16 cells
        self.assertEqual(len(result["cells"]), 16)
        # Verify no duplicates in strength combos
        seen = set()
        for cell in result["cells"]:
            ms = tuple(cell["axis_values"]["lora_model_strengths"])
            cs = tuple(cell["axis_values"]["lora_clip_strengths"])
            seen.add((ms, cs))
        # 2 prompts * 2 seeds * (4 combos) = 16, but 4 unique strength combos
        strength_combos = {(ms, cs) for ms, cs in seen}
        self.assertEqual(len(strength_combos), 4)


# ── D5: Prompt/Image/Workflow-owned interactions ─────────────────────────

class PromptImageWorkflowOwnedTests(unittest.TestCase):
    """D5: Negative prompt resolution order and workflow-owned behavior."""

    def test_per_item_negative_explicit(self):
        """Explicit per-item negative is used."""
        c = load_compiler()
        spec = _minimal_spec()
        spec["prompts"]["items"] = [
            {"id": "p_a", "label": "cat", "text": "a cat",
             "negative": "bad cat", "enabled": True},
        ]
        result = c.compile_experiment(spec)
        for cell in result["cells"]:
            self.assertEqual(cell["negative_prompt"], "bad cat")

    def test_shared_negative_fallback(self):
        """shared_negative applies when per-item negative is absent."""
        c = load_compiler()
        spec = _minimal_spec()
        spec["prompts"]["shared_negative"] = "shared bad"
        for item in spec["prompts"]["items"]:
            del item["negative"]
        result = c.compile_experiment(spec)
        for cell in result["cells"]:
            self.assertEqual(cell["negative_prompt"], "shared bad")

    def test_explicit_empty_clears_workflow(self):
        """Explicit empty string negative clears the workflow negative field."""
        c = load_compiler()
        spec = _minimal_spec()
        spec["prompts"]["items"] = [
            {"id": "p_a", "label": "cat", "text": "a cat",
             "negative": "", "enabled": True},
        ]
        result = c.compile_experiment(spec)
        for cell in result["cells"]:
            self.assertEqual(cell["negative_prompt"], "")

    def test_both_missing_preserves_workflow(self):
        """Neither per-item nor shared negative preserves workflow value."""
        c = load_compiler()
        spec = _minimal_spec()
        spec["prompts"].pop("shared_negative", None)
        for item in spec["prompts"]["items"]:
            del item["negative"]
        result = c.compile_experiment(spec)
        for cell in result["cells"]:
            self.assertTrue(c.is_workflow_owned(cell["negative_prompt"]))

    def test_positive_and_negative_mappings_stay_separate(self):
        """Positive and negative prompt mappings remain distinct in cell output."""
        c = load_compiler()
        spec = _minimal_spec()
        spec["prompts"]["items"] = [
            {"id": "p_a", "label": "cat", "text": "a cat",
             "negative": "bad", "enabled": True},
            {"id": "p_b", "label": "dog", "text": "a dog",
             "negative": "ugly", "enabled": True},
        ]
        result = c.compile_experiment(spec)
        for cell in result["cells"]:
            pid = cell.get("prompt_id", "")
            if pid == "p_a":
                self.assertEqual(cell["prompt"], "a cat")
                self.assertEqual(cell["negative_prompt"], "bad")
            elif pid == "p_b":
                self.assertEqual(cell["prompt"], "a dog")
                self.assertEqual(cell["negative_prompt"], "ugly")


# ═══════════════════════════════════════════════════════════════════════
# Stack – LoRA representability (per-stack LoRA selections)
# ═══════════════════════════════════════════════════════════════════════
#
# These tests define a spec shape where each workflow contains one or
# more "stacks", and each stack carries its own LoRA selections (rather
# than the current global ``loras.selections``).  The compiler must be
# able to represent every combination below.
#
# The helpers keep flat backward-compat fields so the current compiler
# can at least run without crashing, but it will produce wrong results
# because it does not yet understand per-stack LoRA selections.

_STACK_LORA_PROMPTS = {
    "items": [
        {"id": "p1", "label": "txt", "text": "hello",
         "negative": None, "enabled": True},
    ],
}

_STACK_LORA_AXES = {
    "shared": {"seed": {"mode": "list", "values": [42]}},
}


def _stack_lora_spec(stack_configs, prompts=None, axes=None):
    """Build an experiment spec with per-stack LoRA configuration.

    Parameters
    ----------
    stack_configs : list[dict]
        Each entry is a per-stack config with keys:

        - ``stack_id`` (str) — unique stack identifier
        - ``main_triple`` (dict) — ``{"unet": .., "clip": .., "vae": ..}``
        - ``subprofile_triples`` (list, optional)
        - ``selected_triple_ids`` (list, optional)
        - ``lora_selections`` (list) — per-stack LoRA selections

    prompts, axes : dict, optional
        Override defaults.

    The returned spec also carries flat workflow-level fields for
    backward compatibility with the current compiler (which ignores
    ``stacks``).  Global ``loras.selections`` is intentionally empty
    to force the failure: per-stack selections are the only way to
    obtain LoRA cells, but the current compiler does not read them.
    """
    if not stack_configs:
        stack_configs = [{
            "stack_id": "s1",
            "main_triple": {"id": "main", "unet": "u1",
                            "clip": "c1", "vae": "v1"},
            "subprofile_triples": [],
            "selected_triple_ids": ["main"],
            "lora_selections": [],
        }]

    first = stack_configs[0]
    stacks = []
    for sc in stack_configs:
        stacks.append({
            "stack_id": sc.get("stack_id", "s1"),
            "loader_target_group_id": sc.get(
                "loader_target_group_id", "g_default"),
            "main_triple": sc.get(
                "main_triple",
                {"id": "main", "unet": "u1", "clip": "c1", "vae": "v1"},
            ),
            "subprofile_triples": sc.get("subprofile_triples", []),
            "selected_triple_ids": sc.get("selected_triple_ids", ["main"]),
            "lora_selections": sc.get("lora_selections", []),
        })

    return {
        "experiment_id": "exp_stack_lora",
        "revision": 1,
        "workflows": [{
            "profile_id": "p1",
            "stacks": stacks,
            # Flat backward-compat fields (point to first stack)
            "loader_target_group_id": first.get(
                "loader_target_group_id", "g_default"),
            "main_triple": first.get(
                "main_triple",
                {"id": "main", "unet": "u1", "clip": "c1", "vae": "v1"},
            ),
            "subprofile_triples": first.get("subprofile_triples", []),
            "selected_triple_ids": first.get(
                "selected_triple_ids", ["main"]),
            "lora_slots": [],
        }],
        "prompts": prompts or _STACK_LORA_PROMPTS,
        "images": {"mode": "cartesian", "items": []},
        # Intentionally empty — per-stack selections are the source of
        # truth, but the current compiler does not use them yet.
        "loras": {"selections": []},
        "axes": axes or _STACK_LORA_AXES,
    }


def _lora_selection(id_, label, entries=None, enabled=True):
    """Build a single per-stack LoRA selection dict."""
    return {
        "id": id_,
        "label": label,
        "loras": entries or [],
        "enabled": enabled,
    }


def _lora_entry(file, model_strength=None, clip_strength=None,
                enabled=True):
    """Build a single LoRA entry inside a selection."""
    return {
        "file": file,
        "model_strength": model_strength if model_strength else [0.7],
        "clip_strength": clip_strength if clip_strength else [0.7],
        "enabled": enabled,
    }


_NO_LORA_SEL = _lora_selection("L_no", "No LoRA", [])
_WORKFLOW_DEFAULT_SEL = _lora_selection(
    "__workflow_default__", "Workflow Default", [],
)


class StackLoraRepresentabilityTests(unittest.TestCase):
    """The matrix compiler must be able to represent all stack–LoRA
    pairing configurations listed in the backend-adapter contract.

    Each test builds a spec with per-stack LoRA selections (the
    ``workflows[].stacks`` field) and asserts that ``compile_experiment``
    produces cells that correctly reflect the per-stack configuration.

    These tests are expected to FAIL because the current compiler does
    not yet support per-stack LoRA selections.
    """

    # ── Scenario 1 ────────────────────────────────────────────────────
    def test_one_workflow_two_stacks_no_lora(self):
        """One workflow, two stacks, no LoRA.

        Two stacks, both with only "No LoRA".  The compiler should
        produce two checkpoints (one per stack), each with cells
        whose LoRA signature is empty.
        """
        c = load_compiler()
        spec = _stack_lora_spec([
            {"stack_id": "s1", "lora_selections": [_NO_LORA_SEL]},
            {"stack_id": "s2", "lora_selections": [_NO_LORA_SEL]},
        ])
        result = c.compile_experiment(spec)

        # Expect 2 checkpoints (one per stack)
        self.assertEqual(
            len(result["checkpoints"]), 2,
            "Should produce one checkpoint per stack",
        )

        # Every cell must have an empty LoRA signature
        for cell in result["cells"]:
            self.assertEqual(
                cell["lora_signature"], [],
                "No-LoRA cells must have an empty signature",
            )

        # Each checkpoint should list exactly the stack's LoRA selections
        for ck in result["checkpoints"]:
            self.assertEqual(
                ck["lora_selection_ids"], ["L_no"],
            )

    # ── Scenario 2 ────────────────────────────────────────────────────
    def test_one_workflow_one_stack_three_lora_configs(self):
        """One workflow, one stack, three LoRA configurations.

        A single stack with three distinct LoRA selections (including
        'No LoRA').  The compiler must emit cells for all three.
        """
        c = load_compiler()
        lora_a = _lora_selection("L_a", "LoRA A", [
            _lora_entry("a.safetensors"),
        ])
        lora_b = _lora_selection("L_b", "LoRA B", [
            _lora_entry("b.safetensors"),
        ])
        spec = _stack_lora_spec([
            {"stack_id": "s1",
             "lora_selections": [_NO_LORA_SEL, lora_a, lora_b]},
        ])
        result = c.compile_experiment(spec)

        # 1 checkpoint × 3 LoRA selections × 1 prompt × 1 seed = 3
        self.assertEqual(len(result["cells"]), 3)
        seen_ids = {cell["lora_selection_id"] for cell in result["cells"]}
        self.assertEqual(seen_ids, {"L_no", "L_a", "L_b"})

    # ── Scenario 3 ────────────────────────────────────────────────────
    def test_same_loras_across_both_stacks(self):
        """Same LoRAs across both stacks.

        Two stacks, each with the same pair of LoRA selections.
        Each stack independently produces cells for both.
        """
        c = load_compiler()
        lora_a = _lora_selection("L_a", "LoRA A", [
            _lora_entry("a.safetensors"),
        ])
        lora_b = _lora_selection("L_b", "LoRA B", [
            _lora_entry("b.safetensors"),
        ])
        selections = [lora_a, lora_b]
        spec = _stack_lora_spec([
            {"stack_id": "s1", "lora_selections": selections},
            {"stack_id": "s2", "lora_selections": selections},
        ])
        result = c.compile_experiment(spec)

        # 2 stacks × 2 LoRA selections × 1 prompt × 1 seed = 4
        self.assertEqual(len(result["cells"]), 4)

        # Both LoRA IDs must appear across the checkpoint set
        all_ck_lora_ids = set()
        for ck in result["checkpoints"]:
            for lid in ck["lora_selection_ids"]:
                all_ck_lora_ids.add(lid)
        self.assertEqual(all_ck_lora_ids, {"L_a", "L_b"})

    # ── Scenario 4 ────────────────────────────────────────────────────
    def test_loras_on_only_one_stack(self):
        """LoRAs on only one stack.

        Stack one has only "No LoRA"; stack two has two explicit
        selections.  The compiler must not leak explicit LoRAs into
        the first stack's cells.
        """
        c = load_compiler()
        lora_c = _lora_selection("L_c", "LoRA C", [
            _lora_entry("c.safetensors"),
        ])
        lora_d = _lora_selection("L_d", "LoRA D", [
            _lora_entry("d.safetensors"),
        ])
        spec = _stack_lora_spec([
            {"stack_id": "s1", "lora_selections": [_NO_LORA_SEL]},
            {"stack_id": "s2",
             "lora_selections": [lora_c, lora_d]},
        ])
        result = c.compile_experiment(spec)

        # 2 stacks × LoRA-dependent cell counts
        self.assertEqual(len(result["checkpoints"]), 2)

        # Find which checkpoint belongs to which stack
        # (by checking lora_selection_ids on each checkpoint)
        ck_by_lora_count = {}
        for ck in result["checkpoints"]:
            ck_by_lora_count.setdefault(
                tuple(ck["lora_selection_ids"]), []).append(ck)

        # One checkpoint has only "L_no" (the first stack)
        # The other has "L_c" and "L_d" (the second stack)
        self.assertIn(("L_no",), ck_by_lora_count)
        self.assertIn(("L_c", "L_d"), ck_by_lora_count)

    # ── Scenario 5 ────────────────────────────────────────────────────
    def test_different_loras_per_stack(self):
        """Different LoRAs per stack.

        Each stack has a completely different set of LoRA selections.
        Compiler must correctly isolate per-stack selections and
        produce the right LoRA IDs in each checkpoint's cells.
        """
        c = load_compiler()
        lora_x = _lora_selection("L_x", "LoRA X", [
            _lora_entry("x.safetensors"),
        ])
        lora_y = _lora_selection("L_y", "LoRA Y", [
            _lora_entry("y.safetensors"),
        ])
        lora_z = _lora_selection("L_z", "LoRA Z", [
            _lora_entry("z.safetensors"),
        ])
        spec = _stack_lora_spec([
            {"stack_id": "s1", "lora_selections": [lora_x, lora_y]},
            {"stack_id": "s2", "lora_selections": [lora_z]},
        ])
        result = c.compile_experiment(spec)

        # 2 stacks × per-stack LoRA + 1 prompt + 1 seed
        # S1: 2 LoRAs × 1 = 2 cells; S2: 1 LoRA × 1 = 1 cell → 3 total
        self.assertEqual(len(result["cells"]), 3)

        # Group cell LoRA IDs by checkpoint
        ck_cells: dict[str, set] = {}
        for cell in result["cells"]:
            ck_cells.setdefault(cell["checkpoint_id"], set()).add(
                cell["lora_selection_id"])
        # One checkpoint has {L_x, L_y}, the other has {L_z}
        all_sets = [s for s in ck_cells.values()]
        self.assertIn({"L_x", "L_y"}, all_sets)
        self.assertIn({"L_z"}, all_sets)

    # ── Scenario 6 ────────────────────────────────────────────────────
    def test_separate_workflow_local_stack_lora_sets(self):
        """Separate workflow-local stack/LoRA sets.

        Two distinct workflows, each with its own stacks and LoRA
        selections.  LoRA configs must not leak across workflows.
        """
        c = load_compiler()
        # Override workflow-level fixture: two workflows, each with
        # its own stack/LoRA set.
        lora_w1 = _lora_selection("L_w1", "W1-LoRA", [
            _lora_entry("w1.safetensors"),
        ])
        lora_w2 = _lora_selection("L_w2", "W2-LoRA", [
            _lora_entry("w2.safetensors"),
        ])

        spec = _stack_lora_spec([], prompts=_STACK_LORA_PROMPTS,
                                axes=_STACK_LORA_AXES)
        # Replace the single-workflow fixture with two workflows
        spec["workflows"] = [
            {
                "profile_id": "wf1",
                "stacks": [
                    {"stack_id": "s1",
                     "lora_selections": [_NO_LORA_SEL, lora_w1],
                     "main_triple": {"id": "main", "unet": "u1",
                                     "clip": "c1", "vae": "v1"},
                     "subprofile_triples": [],
                     "selected_triple_ids": ["main"],
                     },
                ],
                # Flat backward-compat
                "loader_target_group_id": "g_default",
                "main_triple": {"id": "main", "unet": "u1",
                                "clip": "c1", "vae": "v1"},
                "subprofile_triples": [],
                "selected_triple_ids": ["main"],
                "lora_slots": [],
            },
            {
                "profile_id": "wf2",
                "stacks": [
                    {"stack_id": "s2",
                     "lora_selections": [lora_w2],
                     "main_triple": {"id": "main", "unet": "u2",
                                     "clip": "c2", "vae": "v2"},
                     "subprofile_triples": [],
                     "selected_triple_ids": ["main"],
                     },
                ],
                # Flat backward-compat
                "loader_target_group_id": "g_default",
                "main_triple": {"id": "main", "unet": "u2",
                                "clip": "c2", "vae": "v2"},
                "subprofile_triples": [],
                "selected_triple_ids": ["main"],
                "lora_slots": [],
            },
        ]

        result = c.compile_experiment(spec)

        # 2 workflows × 1 stack each
        self.assertEqual(len(result["checkpoints"]), 2)

        # Collect LoRA IDs per profile
        lora_by_profile: dict[str, set] = {}
        for cell in result["cells"]:
            lora_by_profile.setdefault(cell["profile_id"], set()).add(
                cell["lora_selection_id"])

        self.assertIn("wf1", lora_by_profile)
        self.assertIn("wf2", lora_by_profile)
        self.assertEqual(lora_by_profile["wf1"], {"L_no", "L_w1"})
        self.assertEqual(lora_by_profile["wf2"], {"L_w2"})

    # ── Scenario 7 ────────────────────────────────────────────────────
    def test_no_lora_alongside_explicit_lora(self):
        """"No LoRA" alongside explicit LoRA.

        A single stack that has both a "No LoRA" selection and an
        explicit LoRA.  The compiler must emit cells for both.
        """
        c = load_compiler()
        lora_e = _lora_selection("L_e", "Explicit", [
            _lora_entry("e.safetensors"),
        ])
        spec = _stack_lora_spec([
            {"stack_id": "s1",
             "lora_selections": [_NO_LORA_SEL, lora_e]},
        ])
        result = c.compile_experiment(spec)

        # 1 checkpoint × 2 LoRA selections × 1 prompt × 1 seed = 2
        self.assertEqual(len(result["cells"]), 2)

        seen_ids = {cell["lora_selection_id"] for cell in result["cells"]}
        self.assertEqual(seen_ids, {"L_no", "L_e"})

        # Cells with lora_selection_id == "L_no" must have empty signature
        for cell in result["cells"]:
            if cell["lora_selection_id"] == "L_no":
                self.assertEqual(cell["lora_signature"], [])
            else:
                self.assertGreater(len(cell["lora_signature"]), 0)

    # ── Scenario 8 ────────────────────────────────────────────────────
    def test_workflow_default_alongside_explicit_lora(self):
        """"Workflow Default" alongside explicit LoRA.

        A single stack that has both a "Workflow Default" selection
        and an explicit LoRA.  The "Workflow Default" cells must
        carry the WORKFLOW_OWNED sentinel or an equivalent marker.
        """
        c = load_compiler()
        lora_f = _lora_selection("L_f", "Explicit", [
            _lora_entry("f.safetensors"),
        ])
        spec = _stack_lora_spec([
            {"stack_id": "s1",
             "lora_selections": [_WORKFLOW_DEFAULT_SEL, lora_f]},
        ])
        result = c.compile_experiment(spec)

        # 1 checkpoint × 2 LoRA selections × 1 prompt × 1 seed = 2
        self.assertEqual(len(result["cells"]), 2)

        seen_ids = {cell["lora_selection_id"] for cell in result["cells"]}
        self.assertEqual(seen_ids, {"__workflow_default__", "L_f"})

    # ── Scenario 9 ────────────────────────────────────────────────────
    def test_lora_strength_sweeps(self):
        """LoRA strength sweeps.

        A single stack with a single LoRA that has multiple model
        and clip strength values, producing a Cartesian product of
        strength combinations per cell.
        """
        c = load_compiler()
        sweep_lora = _lora_selection("L_sweep", "Sweep", [
            _lora_entry("sweep.safetensors",
                        model_strength=[0.5, 1.0],
                        clip_strength=[0.3, 0.8]),
        ])
        spec = _stack_lora_spec([
            {"stack_id": "s1", "lora_selections": [sweep_lora]},
        ])
        result = c.compile_experiment(spec)

        # 1 checkpoint × 1 LoRA selection × 4 strength combos (2×2)
        # × 1 prompt × 1 seed = 4
        self.assertEqual(len(result["cells"]), 4)

        # Verify all four strength combinations are present.
        # Each cell stores strengths as lists (for multi-LoRA compatibility);
        # extract the scalar with [0] for single-LoRA assertions.
        seen = set()
        for cell in result["cells"]:
            ms = cell["axis_values"]["lora_model_strengths"][0]
            cs = cell["axis_values"]["lora_clip_strengths"][0]
            seen.add((ms, cs))
        self.assertEqual(
            seen,
            {(0.5, 0.3), (0.5, 0.8), (1.0, 0.3), (1.0, 0.8)},
        )

    # ── Scenario 10 ───────────────────────────────────────────────────
    def test_per_workflow_extra_axis_overrides_shared(self):
        """When an extra (non-internal) axis appears in both shared and
        per_workflow, per_workflow values must be used, matching normal-axis
        override semantics (shared first, per_workflow wins)."""
        c = load_compiler()
        spec = _minimal_spec()
        # Add a custom extra axis to both shared and per_workflow with
        # different values — per_workflow [99] must win over shared [1, 2].
        spec["axes"]["shared"]["my_custom_param"] = {"mode": "list", "values": [1, 2]}
        spec["axes"]["per_workflow"]["p1"]["my_custom_param"] = {"mode": "list", "values": [99]}
        result = c.compile_experiment(spec)
        for cell in result["cells"]:
            self.assertEqual(
                cell["axis_values"]["my_custom_param"], 99,
                "per_workflow extra axis value must override shared value"
            )

    def test_controlled_lora_config_one_per_workflow(self):
        """Controlled LoRA configuration, one per workflow.

        Each workflow has a single controlled LoRA selection.  The
        compiler must not mix selections from different workflows.
        """
        c = load_compiler()
        lora_g = _lora_selection("L_g", "Controlled-G", [
            _lora_entry("g.safetensors"),
        ])
        lora_h = _lora_selection("L_h", "Controlled-H", [
            _lora_entry("h.safetensors"),
        ])

        spec = _stack_lora_spec([], prompts=_STACK_LORA_PROMPTS,
                                axes=_STACK_LORA_AXES)
        spec["workflows"] = [
            {
                "profile_id": "wf_a",
                "stacks": [
                    {"stack_id": "s1",
                     "lora_selections": [lora_g],
                     "main_triple": {"id": "main", "unet": "u1",
                                     "clip": "c1", "vae": "v1"},
                     "subprofile_triples": [],
                     "selected_triple_ids": ["main"],
                     },
                ],
                "loader_target_group_id": "g_default",
                "main_triple": {"id": "main", "unet": "u1",
                                "clip": "c1", "vae": "v1"},
                "subprofile_triples": [],
                "selected_triple_ids": ["main"],
                "lora_slots": [],
            },
            {
                "profile_id": "wf_b",
                "stacks": [
                    {"stack_id": "s2",
                     "lora_selections": [lora_h],
                     "main_triple": {"id": "main", "unet": "u2",
                                     "clip": "c2", "vae": "v2"},
                     "subprofile_triples": [],
                     "selected_triple_ids": ["main"],
                     },
                ],
                "loader_target_group_id": "g_default",
                "main_triple": {"id": "main", "unet": "u2",
                                "clip": "c2", "vae": "v2"},
                "subprofile_triples": [],
                "selected_triple_ids": ["main"],
                "lora_slots": [],
            },
        ]

        result = c.compile_experiment(spec)

        # Each workflow has 1 stack × 1 LoRA × 1 prompt × 1 seed → 1 cell
        # 2 workflows → 2 cells
        self.assertEqual(len(result["cells"]), 2)

        # LoRA IDs must be isolated per workflow
        ids_by_profile: dict[str, set] = {}
        for cell in result["cells"]:
            ids_by_profile.setdefault(cell["profile_id"], set()).add(
                cell["lora_selection_id"])
        self.assertEqual(ids_by_profile.get("wf_a", set()), {"L_g"})
        self.assertEqual(ids_by_profile.get("wf_b", set()), {"L_h"})


if __name__ == "__main__":
    unittest.main()
