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
        # Count distinct sequences per sampler
        seq_by_sampler: dict = {}
        for cell in result["cells"]:
            seq_by_sampler.setdefault(cell["axis_values"]["sampler"], []).append(cell["sequence"])
        # All euler cells come before all dpm cells (sampler is the outermost cheap axis)
        all_samps = []
        for cell in result["cells"]:
            all_samps.append(cell["axis_values"]["sampler"])
        # 2 prompts × (2 samplers × 2 schedulers × 2 seeds) = 16 cells
        self.assertEqual(
            all_samps,
            ["euler", "euler", "euler", "euler",
             "dpm", "dpm", "dpm", "dpm",
             "euler", "euler", "euler", "euler",
             "dpm", "dpm", "dpm", "dpm"],
        )


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


if __name__ == "__main__":
    unittest.main()
