"""Tests for the future experiment_setup_adapter module.

These tests will fail because experiment_setup_adapter.py does not yet exist.
They define the expected contract for the backend authoritative adapter
that will normalise legacy profiles, validate normalised drafts, and
attach profile metadata before the matrix compiler runs.

Each test calls ``load_setup_adapter()`` which raises AssertionError when
the module is missing — the expected "adapter support is missing" signal.
"""
import importlib.util
import sys
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
ADAPTER_PATH = REPO_ROOT / "experiment_setup_adapter.py"


def load_setup_adapter():
    """Load the experiment_setup_adapter module.

    Raises AssertionError when the module is missing — this is the
    expected failure signal that backend adapter support has not been
    implemented yet.
    """
    if not ADAPTER_PATH.exists():
        raise AssertionError(
            "experiment_setup_adapter.py missing — "
            "backend authoritative adapter not yet implemented"
        )
    spec = importlib.util.spec_from_file_location(
        "experiment_setup_adapter", ADAPTER_PATH
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


# ── 1. Normalised-draft validation entry points ────────────────────────

class NormalizedDraftValidationTests(unittest.TestCase):
    """The backend adapter must expose a ``validate_normalized_draft`` entry
    point that validates a normalised experiment draft before the compiler
    consumes it.  The validation should check structural completeness and
    reject malformed drafts with a structured error report."""

    def test_validate_normalized_draft_is_callable(self):
        """``validate_normalized_draft`` must be a callable on the module."""
        adapter = load_setup_adapter()
        self.assertTrue(
            callable(adapter.validate_normalized_draft),
        )

    def test_validate_normalized_draft_accepts_well_formed_draft(self):
        """A well-formed normalised draft must pass validation."""
        adapter = load_setup_adapter()
        draft = {
            "experiment_id": "exp_1",
            "revision": 1,
            "profile_type": "t2i",
            "workflows": [{
                "profile_id": "p1",
                "stacks": [{
                    "stack_id": "s1",
                    "loader_target_group_id": "g_default",
                    "main_triple": {"unet": "u1", "clip": "c1", "vae": "v1"},
                    "selected_triple_ids": ["main"],
                    "lora_selections": [],
                }],
            }],
            "prompts": {"items": [{"text": "hello", "enabled": True}]},
            "axes": {"shared": {"seed": {"mode": "list", "values": [1]}}},
        }
        result = adapter.validate_normalized_draft(draft)
        self.assertIsInstance(result, dict)
        self.assertTrue(result.get("valid", False))

    def test_validate_normalized_draft_rejects_empty_experiment_id(self):
        """An empty experiment_id must fail validation."""
        adapter = load_setup_adapter()
        draft = {
            "experiment_id": "",
            "revision": 1,
            "profile_type": "t2i",
            "workflows": [],
        }
        result = adapter.validate_normalized_draft(draft)
        self.assertIsInstance(result, dict)
        self.assertFalse(result.get("valid", True))
        self.assertIn("experiment_id", str(result.get("errors", "")))


# ── 2. Legacy profile normalisation ────────────────────────────────────

class LegacyProfileNormalizationTests(unittest.TestCase):
    """Legacy profiles (schema_version < 2) must be normalised to a
    deterministic *profile_type*: ``"t2i"`` for text-to-image profiles
    without input images, or ``"legacy_default"`` for profiles whose
    capabilities are ambiguous."""

    def test_legacy_t2i_profile_detects_t2i(self):
        """A legacy profile with txt2img capability and no input_image
        slot must normalise to ``"t2i"``."""
        adapter = load_setup_adapter()
        profile = {
            "id": "legacy_p1",
            "schema_version": 1,
            "capabilities": {"txt2img": True, "img2img": False},
            "slots": {},
            "model_stack": {"lora": [], "checkpoint": ["ckpt1"]},
        }
        normalised = adapter.normalize_legacy_profile(profile)
        self.assertEqual(normalised["profile_type"], "t2i")

    def test_legacy_default_profile_type(self):
        """A legacy profile without clear txt2img-only capability must
        normalise to ``"legacy_default"``."""
        adapter = load_setup_adapter()
        profile = {
            "id": "legacy_p2",
            "schema_version": 1,
            "capabilities": {},
            "slots": {"input_image": {"node_id": "10"}},
            "model_stack": {"lora": [], "checkpoint": ["ckpt1"]},
        }
        normalised = adapter.normalize_legacy_profile(profile)
        self.assertEqual(normalised["profile_type"], "legacy_default")

    def test_legacy_with_lora_normalises(self):
        """A legacy profile with LoRA stack entries must still
        normalise (not crash) and produce a ``profile_type``."""
        adapter = load_setup_adapter()
        profile = {
            "id": "legacy_lora",
            "schema_version": 1,
            "capabilities": {"txt2img": True},
            "slots": {},
            "model_stack": {
                "checkpoint": ["ckpt1"],
                "lora": ["lora_a.safetensors", "lora_b.safetensors"],
            },
        }
        normalised = adapter.normalize_legacy_profile(profile)
        self.assertIn("profile_type", normalised)
        self.assertIn("lora_entries", normalised)

    def test_normalize_legacy_is_idempotent(self):
        """Calling ``normalize_legacy_profile`` twice on the same input
        must return the same result."""
        adapter = load_setup_adapter()
        profile = {
            "id": "legacy_idem",
            "schema_version": 1,
            "capabilities": {"txt2img": True},
            "slots": {},
        }
        first = adapter.normalize_legacy_profile(profile)
        second = adapter.normalize_legacy_profile(first)
        self.assertEqual(first, second)


# ── 3. No-rewrite-on-load expectation ──────────────────────────────────

class NoRewriteOnLoadTests(unittest.TestCase):
    """Legacy profiles must not be written back to disk when loaded.
    The ``load_legacy_profile`` function should return a flag indicating
    whether the loaded data was rewritten, defaulting to False."""

    def test_load_legacy_profile_returns_not_rewritten(self):
        """``load_legacy_profile`` must return a dict with a ``rewritten``
        key set to False for an already-normalised profile."""
        adapter = load_setup_adapter()
        profile_data = {
            "id": "p1",
            "schema_version": 2,
            "profile_type": "t2i",
        }
        result = adapter.load_legacy_profile(profile_data)
        self.assertIsInstance(result, dict)
        self.assertFalse(result.get("rewritten", True))

    def test_load_legacy_profile_rewritten_flag_is_false_for_legacy(self):
        """Even a legacy profile (schema_version < 2) loaded via
        ``load_legacy_profile`` must report ``rewritten=False``
        to confirm that loading did *not* touch the file on disk."""
        adapter = load_setup_adapter()
        profile_data = {
            "id": "legacy_p",
            "schema_version": 1,
            "capabilities": {"txt2img": True},
            "slots": {},
        }
        result = adapter.load_legacy_profile(profile_data)
        self.assertFalse(result.get("rewritten", True))


# ── 4. Stale profile revision / hash detection ─────────────────────────

class StaleProfileDetectionTests(unittest.TestCase):
    """The adapter must detect when a stored profile is stale based on
    its revision number or workflow hash compared to the current state."""

    def test_is_profile_stale_revision_mismatch(self):
        """A profile with a lower revision than the expected current
        version must be reported as stale."""
        adapter = load_setup_adapter()
        profile = {"revision": 1, "workflow_hash": "abc"}
        current = {"revision": 2, "workflow_hash": "abc"}
        self.assertTrue(adapter.is_profile_stale(profile, current))

    def test_is_profile_stale_hash_mismatch(self):
        """A profile with a different workflow_hash than the current
        workflow must be reported as stale even if revision matches."""
        adapter = load_setup_adapter()
        profile = {"revision": 2, "workflow_hash": "old_hash"}
        current = {"revision": 2, "workflow_hash": "new_hash"}
        self.assertTrue(adapter.is_profile_stale(profile, current))

    def test_is_profile_not_stale_when_current(self):
        """A profile matching both revision and hash must NOT be
        reported as stale."""
        adapter = load_setup_adapter()
        profile = {"revision": 2, "workflow_hash": "current_hash"}
        current = {"revision": 2, "workflow_hash": "current_hash"}
        self.assertFalse(adapter.is_profile_stale(profile, current))

    def test_stale_detection_does_not_mutate_inputs(self):
        """``is_profile_stale`` must not modify the input dicts."""
        adapter = load_setup_adapter()
        profile = {"revision": 1, "workflow_hash": "a"}
        current = {"revision": 2, "workflow_hash": "b"}
        profile_copy = dict(profile)
        current_copy = dict(current)
        _ = adapter.is_profile_stale(profile, current)
        self.assertEqual(profile, profile_copy)
        self.assertEqual(current, current_copy)


# ── 5. Null controlled-value handling ──────────────────────────────────

class NullControlledValueTests(unittest.TestCase):
    """The adapter must handle ``None`` (null) controlled values
    gracefully — they should be mapped to a no-op sentinel or
    silently dropped, never raise TypeError."""

    def test_null_controlled_value_does_not_raise(self):
        """``normalize_controlled_values`` with a ``None`` value must
        not raise and must return a valid result."""
        adapter = load_setup_adapter()
        spec = {"controlled_value": None}
        result = adapter.normalize_controlled_values(spec)
        self.assertIsNotNone(result)

    def test_null_in_nested_controlled_value(self):
        """``None`` in a nested controlled-values dict must be handled
        without raising."""
        adapter = load_setup_adapter()
        spec = {"axes": {"controlled": {"sampler": None, "steps": 20}}}
        result = adapter.normalize_controlled_values(spec)
        self.assertIn("axes", result)

    def test_null_controlled_value_in_selection_list(self):
        """A list of controlled values containing ``None`` entries must
        not cause index errors."""
        adapter = load_setup_adapter()
        spec = {"loras": {"selections": [None, {"id": "L_a", "loras": []}]}}
        result = adapter.normalize_controlled_values(spec)
        self.assertIn("loras", result)


# ── 6. Normalised dimension attachment ─────────────────────────────────

class NormalizedDimensionAttachmentTests(unittest.TestCase):
    """The adapter must attach resolution (width × height) from a
    profile's defaults or saved state to a normalised draft so the
    compiler downstream does not need to re-parse the profile."""

    def test_dimensions_attached_from_profile_defaults(self):
        """``attach_profile_dimensions`` must attach width/height from
        profile defaults to the normalised draft."""
        adapter = load_setup_adapter()
        draft = {"experiment_id": "exp_1"}
        profile = {"default_width": 1024, "default_height": 768}
        result = adapter.attach_profile_dimensions(draft, profile)
        self.assertIn("resolution", result)
        w, h = result["resolution"]
        self.assertEqual(w, 1024)
        self.assertEqual(h, 768)

    def test_dimensions_attached_from_saved_state(self):
        """If the profile has a saved state with dimensions, those
        must take priority over defaults."""
        adapter = load_setup_adapter()
        draft = {"experiment_id": "exp_1"}
        profile = {
            "default_width": 512,
            "default_height": 512,
            "saved_state": {"width": 1920, "height": 1080},
        }
        result = adapter.attach_profile_dimensions(draft, profile)
        w, h = result["resolution"]
        self.assertEqual(w, 1920)
        self.assertEqual(h, 1080)

    def test_dimensions_attached_do_not_override_existing(self):
        """If the draft already has a resolution, it must be preserved
        (the adapter should not blindly overwrite)."""
        adapter = load_setup_adapter()
        draft = {"experiment_id": "exp_1", "resolution": (640, 480)}
        profile = {"default_width": 1024, "default_height": 768}
        result = adapter.attach_profile_dimensions(draft, profile)
        w, h = result["resolution"]
        self.assertEqual(w, 640)
        self.assertEqual(h, 480)

    def test_dimensions_fallback_when_profile_missing(self):
        """When the profile has no resolution data, the draft must
        remain unchanged (no crash, no spurious keys)."""
        adapter = load_setup_adapter()
        draft = {"experiment_id": "exp_1"}
        profile = {}
        result = adapter.attach_profile_dimensions(draft, profile)
        self.assertNotIn("resolution", result)

    def test_dimensions_validate_positive_integers(self):
        """Invalid stored dimensions should be rejected rather than silently accepted."""
        adapter = load_setup_adapter()
        draft = {}
        profile = {"default_width": -1, "default_height": 768}
        with self.assertRaises((ValueError, AssertionError)):
            adapter.attach_profile_dimensions(draft, profile)


# ═══════════════════════════════════════════════════════════════════════
# 7. Normalised draft → compiler spec translation
# ═══════════════════════════════════════════════════════════════════════

class NormalizedDraftTranslationTests(unittest.TestCase):
    """The adapter must expose a ``normalized_draft_to_compiler_spec`` path
    that converts a normalised draft into a spec the matrix compiler can
    consume, preserving per-stack LoRA selections."""

    def test_to_compiler_spec_is_callable(self):
        adapter = load_setup_adapter()
        self.assertTrue(callable(adapter.normalized_draft_to_compiler_spec))

    def test_to_compiler_spec_basic(self):
        adapter = load_setup_adapter()
        draft = {
            "experiment_id": "exp_1",
            "revision": 1,
            "profile_type": "t2i",
            "workflows": [{
                "profile_id": "p1",
                "stacks": [{
                    "stack_id": "s1",
                    "loader_target_group_id": "g_default",
                    "main_triple": {"unet": "u1", "clip": "c1", "vae": "v1"},
                    "selected_triple_ids": ["main"],
                    "lora_selections": [],
                }],
            }],
            "prompts": {"items": [{"text": "hello", "enabled": True}]},
            "axes": {"shared": {"seed": {"mode": "list", "values": [1]}}},
        }
        spec = adapter.normalized_draft_to_compiler_spec(draft)
        self.assertIsInstance(spec, dict)
        self.assertEqual(spec["experiment_id"], "exp_1")
        self.assertIn("workflows", spec)
        self.assertEqual(len(spec["workflows"]), 1)
        # Stacks must be preserved
        wf = spec["workflows"][0]
        self.assertIn("stacks", wf)
        self.assertEqual(len(wf["stacks"]), 1)
        # Flat backward-compat fields from first stack
        self.assertEqual(wf["loader_target_group_id"], "g_default")
        self.assertIn("prompts", spec)
        self.assertIn("images", spec)
        self.assertIn("axes", spec)

    def test_to_compiler_spec_preserves_per_stack_lora(self):
        """Per-stack lora selections are preserved in the translated spec."""
        adapter = load_setup_adapter()
        draft = {
            "experiment_id": "exp_2",
            "revision": 1,
            "profile_type": "t2i",
            "workflows": [{
                "profile_id": "p1",
                "stacks": [{
                    "stack_id": "s1",
                    "loader_target_group_id": "g_default",
                    "main_triple": {"unet": "u1", "clip": "c1", "vae": "v1"},
                    "selected_triple_ids": ["main"],
                    "lora_selections": [
                        {"id": "L_no", "label": "No LoRA", "loras": [], "enabled": True},
                        {"id": "L_a", "label": "A", "loras": [
                            {"file": "a.safetensors", "model_strength": [0.7],
                             "clip_strength": [0.7], "enabled": True},
                        ], "enabled": True},
                    ],
                }],
            }],
            "prompts": {"items": [{"text": "hello", "enabled": True}]},
            "axes": {"shared": {"seed": {"mode": "list", "values": [42]}}},
        }
        spec = adapter.normalized_draft_to_compiler_spec(draft)
        stacks = spec["workflows"][0]["stacks"]
        self.assertEqual(len(stacks[0]["lora_selections"]), 2)
        ids = [s["id"] for s in stacks[0]["lora_selections"]]
        self.assertIn("L_no", ids)
        self.assertIn("L_a", ids)

    def test_to_compiler_spec_compiles(self):
        """Spec produced from a normalised draft must compile via matrix compiler."""
        adapter = load_setup_adapter()
        draft = {
            "experiment_id": "exp_compile",
            "revision": 1,
            "profile_type": "t2i",
            "workflows": [{
                "profile_id": "p1",
                "stacks": [{
                    "stack_id": "s1",
                    "loader_target_group_id": "g_default",
                    "main_triple": {"id": "main", "unet": "u1", "clip": "c1", "vae": "v1"},
                    "selected_triple_ids": ["main"],
                    "lora_selections": [
                        {"id": "L_no", "label": "No LoRA", "loras": [], "enabled": True},
                    ],
                }],
            }],
            "prompts": {"items": [
                {"id": "p_a", "label": "cat", "text": "a cat", "negative": None, "enabled": True},
            ]},
            "images": {"mode": "cartesian", "items": []},
            "axes": {"shared": {"seed": {"mode": "list", "values": [42]}}},
        }
        spec = adapter.normalized_draft_to_compiler_spec(draft)
        from matrix_compiler import compile_experiment
        result = compile_experiment(spec)
        self.assertIn("cells", result)
        self.assertGreater(len(result["cells"]), 0)


# ═══════════════════════════════════════════════════════════════════════
# 8. Normalised runtime profile view
# ═══════════════════════════════════════════════════════════════════════

class NormalizedRuntimeProfileTests(unittest.TestCase):
    """The adapter must expose ``build_normalized_runtime_profile`` that
    returns a deterministic, lightweight, in-memory view without full
    legacy payload duplication."""

    def test_build_runtime_profile_is_callable(self):
        adapter = load_setup_adapter()
        self.assertTrue(callable(adapter.build_normalized_runtime_profile))

    def test_runtime_profile_type_from_legacy(self):
        """A legacy T2I profile gets runtime_profile_type 't2i'."""
        adapter = load_setup_adapter()
        profile = {
            "id": "p1",
            "schema_version": 1,
            "capabilities": {"txt2img": True, "img2img": False},
            "slots": {},
            "model_stack": {"checkpoint": ["ckpt1"], "lora": []},
        }
        runtime = adapter.build_normalized_runtime_profile(profile)
        self.assertEqual(runtime["runtime_profile_type"], "t2i")

    def test_runtime_profile_type_legacy_default(self):
        """A legacy profile with input_image gets 'legacy_default'."""
        adapter = load_setup_adapter()
        profile = {
            "id": "p2",
            "schema_version": 1,
            "capabilities": {},
            "slots": {"input_image": {"node_id": "10"}},
            "model_stack": {"checkpoint": ["ckpt1"]},
        }
        runtime = adapter.build_normalized_runtime_profile(profile)
        self.assertEqual(runtime["runtime_profile_type"], "legacy_default")

    def test_runtime_profile_includes_capabilities(self):
        """Capabilities are inferred and present in the runtime view."""
        adapter = load_setup_adapter()
        profile = {
            "id": "p1",
            "schema_version": 1,
            "capabilities": {"txt2img": True},
            "slots": {"prompt": {"node_id": "6", "path": ["inputs", "text"]}},
            "model_stack": {"checkpoint": ["ckpt1"]},
        }
        runtime = adapter.build_normalized_runtime_profile(profile)
        self.assertIn("capabilities", runtime)
        self.assertIsInstance(runtime["capabilities"], dict)
        # txt2img should be True for this profile
        caps = runtime["capabilities"]
        self.assertIn("txt2img", caps)

    def test_runtime_profile_synthesized_stack(self):
        """Profile with model checkpoint gets a synthesized stack."""
        adapter = load_setup_adapter()
        profile = {
            "id": "p1",
            "schema_version": 2,
            "profile_type": "t2i",
            "model_stack": {
                "checkpoint": ["ckpt1"],
                "lora": ["lora_a.safetensors"],
            },
        }
        runtime = adapter.build_normalized_runtime_profile(profile)
        self.assertIn("synthesized_stacks", runtime)
        self.assertIsInstance(runtime["synthesized_stacks"], list)

    def test_runtime_profile_omits_legacy_payload(self):
        """The normalized runtime view must NOT duplicate the full legacy payload."""
        adapter = load_setup_adapter()
        profile = {
            "id": "p1",
            "schema_version": 1,
            "capabilities": {"txt2img": True},
            "slots": {},
            "model_stack": {"checkpoint": ["ckpt1"], "lora": ["l_a", "l_b"]},
            "default_width": 1024,
            "default_height": 768,
        }
        runtime = adapter.build_normalized_runtime_profile(profile)
        # Must not contain full legacy fields
        self.assertNotIn("model_stack", runtime)
        self.assertNotIn("slots", runtime)
        self.assertNotIn("schema_version", runtime)
        # Must contain the normalized view keys
        self.assertIn("runtime_profile_type", runtime)
        self.assertIn("capabilities", runtime)
        self.assertIn("synthesized_stacks", runtime)

    def test_runtime_profile_no_mutation(self):
        """build_normalized_runtime_profile must not mutate the input."""
        adapter = load_setup_adapter()
        original = {
            "id": "p1",
            "schema_version": 1,
            "capabilities": {"txt2img": True},
            "slots": {},
        }
        before = dict(original)
        _ = adapter.build_normalized_runtime_profile(original)
        self.assertEqual(original, before)


# ═══════════════════════════════════════════════════════════════════════
# 9. Richer normalised draft validation (final-ish schema coverage)
# ═══════════════════════════════════════════════════════════════════════

class RichSchemaValidationTests(unittest.TestCase):
    """``validate_normalized_draft`` must cover the final-ish normalised
    schema fields so malformed bypass payloads are rejected."""

    # ── generation_type ────────────────────────────────────────────────

    def test_accepts_generation_type_t2i(self):
        adapter = load_setup_adapter()
        draft = _minimal_rich_draft(overrides={"generation_type": "t2i"})
        result = adapter.validate_normalized_draft(draft)
        self.assertTrue(result.get("valid"), msg=result.get("errors", ""))

    def test_accepts_generation_type_img2img(self):
        adapter = load_setup_adapter()
        draft = _minimal_rich_draft(overrides={"generation_type": "img2img"})
        result = adapter.validate_normalized_draft(draft)
        self.assertTrue(result.get("valid"), msg=result.get("errors", ""))

    def test_rejects_invalid_generation_type(self):
        adapter = load_setup_adapter()
        draft = _minimal_rich_draft(overrides={"generation_type": "bogus"})
        result = adapter.validate_normalized_draft(draft)
        self.assertFalse(result.get("valid", True))
        self.assertIn("generation_type", str(result.get("errors", "")))

    # ── prompt_image_pairing ───────────────────────────────────────────

    def test_accepts_valid_pairing_modes(self):
        adapter = load_setup_adapter()
        for mode in ("cartesian", "paired", "none"):
            draft = _minimal_rich_draft(overrides={
                "prompt_image_pairing": mode,
            })
            result = adapter.validate_normalized_draft(draft)
            self.assertTrue(result.get("valid"),
                            msg=f"mode={mode}: {result.get('errors', '')}")

    def test_rejects_invalid_pairing_mode(self):
        adapter = load_setup_adapter()
        draft = _minimal_rich_draft(overrides={
            "prompt_image_pairing": "invalid_mode",
        })
        result = adapter.validate_normalized_draft(draft)
        self.assertFalse(result.get("valid", True))
        self.assertIn("prompt_image_pairing", str(result.get("errors", "")))

    # ── variable_modes ─────────────────────────────────────────────────

    def test_accepts_valid_variable_modes(self):
        adapter = load_setup_adapter()
        draft = _minimal_rich_draft(overrides={
            "variable_modes": {
                "prompt": {"mode": "independent", "enabled": True},
                "seed": {"mode": "sweep", "enabled": True},
            },
        })
        result = adapter.validate_normalized_draft(draft)
        self.assertTrue(result.get("valid"), msg=result.get("errors", ""))

    def test_rejects_malformed_variable_modes(self):
        adapter = load_setup_adapter()
        draft = _minimal_rich_draft(overrides={
            "variable_modes": "not-a-dict",
        })
        result = adapter.validate_normalized_draft(draft)
        self.assertFalse(result.get("valid", True))

    # ── tested_values ──────────────────────────────────────────────────

    def test_accepts_valid_tested_values(self):
        adapter = load_setup_adapter()
        draft = _minimal_rich_draft(overrides={
            "tested_values": {
                "seed": [42, 99],
                "steps": [20, 30],
            },
        })
        result = adapter.validate_normalized_draft(draft)
        self.assertTrue(result.get("valid"), msg=result.get("errors", ""))

    def test_rejects_malformed_tested_values(self):
        adapter = load_setup_adapter()
        draft = _minimal_rich_draft(overrides={
            "tested_values": "not-a-dict",
        })
        result = adapter.validate_normalized_draft(draft)
        self.assertFalse(result.get("valid", True))

    # ── controlled_values ──────────────────────────────────────────────

    def test_accepts_valid_controlled_values(self):
        adapter = load_setup_adapter()
        draft = _minimal_rich_draft(overrides={
            "controlled_values": {
                "sampler": {"fixed": "euler"},
                "scheduler": {"fixed": "normal"},
            },
        })
        result = adapter.validate_normalized_draft(draft)
        self.assertTrue(result.get("valid"), msg=result.get("errors", ""))

    def test_rejects_malformed_controlled_values(self):
        adapter = load_setup_adapter()
        draft = _minimal_rich_draft(overrides={
            "controlled_values": ["not-a-dict"],
        })
        result = adapter.validate_normalized_draft(draft)
        self.assertFalse(result.get("valid", True))

    # ── compatibility_mode ─────────────────────────────────────────────

    def test_accepts_valid_compatibility_mode(self):
        adapter = load_setup_adapter()
        draft = _minimal_rich_draft(overrides={
            "compatibility_mode": "strict",
        })
        result = adapter.validate_normalized_draft(draft)
        self.assertTrue(result.get("valid"), msg=result.get("errors", ""))

    def test_rejects_invalid_compatibility_mode(self):
        adapter = load_setup_adapter()
        draft = _minimal_rich_draft(overrides={
            "compatibility_mode": 42,
        })
        result = adapter.validate_normalized_draft(draft)
        self.assertFalse(result.get("valid", True))

    # ── advanced_execution ─────────────────────────────────────────────

    def test_accepts_valid_advanced_execution(self):
        adapter = load_setup_adapter()
        draft = _minimal_rich_draft(overrides={
            "advanced_execution": {
                "execution_mode": "parallel",
                "max_parallel": 2,
            },
        })
        result = adapter.validate_normalized_draft(draft)
        self.assertTrue(result.get("valid"), msg=result.get("errors", ""))

    def test_rejects_malformed_advanced_execution(self):
        adapter = load_setup_adapter()
        draft = _minimal_rich_draft(overrides={
            "advanced_execution": "not-a-dict",
        })
        result = adapter.validate_normalized_draft(draft)
        self.assertFalse(result.get("valid", True))

    # ── Full well-formed rich draft ────────────────────────────────────

    def test_accepts_fully_formed_rich_draft(self):
        """A draft with all final-ish fields must pass validation."""
        adapter = load_setup_adapter()
        draft = _minimal_rich_draft()
        result = adapter.validate_normalized_draft(draft)
        if not result.get("valid"):
            self.fail(f"rich draft failed validation: {result.get('errors', '')}")

    # ── Simple fixture shape still accepted (backward compat) ──────────

    def test_simple_fixture_still_accepted(self):
        """The original simple test fixture shape still passes validation."""
        adapter = load_setup_adapter()
        draft = {
            "experiment_id": "exp_fixture",
            "revision": 1,
            "profile_type": "t2i",
            "workflows": [{
                "profile_id": "p1",
                "stacks": [{
                    "stack_id": "s1",
                    "loader_target_group_id": "g_default",
                    "main_triple": {"unet": "u1", "clip": "c1", "vae": "v1"},
                    "selected_triple_ids": ["main"],
                    "lora_selections": [],
                }],
            }],
            "prompts": {"items": [{"text": "hello", "enabled": True}]},
            "axes": {"shared": {"seed": {"mode": "list", "values": [1]}}},
        }
        result = adapter.validate_normalized_draft(draft)
        self.assertTrue(result.get("valid"), msg=result.get("errors", ""))


def _minimal_rich_draft(overrides: dict | None = None) -> dict:
    """Build a minimal but well-formed rich normalised draft."""
    draft = {
        "experiment_id": "exp_rich",
        "revision": 1,
        "generation_type": "t2i",
        "profile_type": "t2i",
        "prompt_image_pairing": "cartesian",
        "workflows": [{
            "profile_id": "p1",
            "stacks": [{
                "stack_id": "s1",
                "loader_target_group_id": "g_default",
                "main_triple": {"unet": "u1", "clip": "c1", "vae": "v1"},
                "selected_triple_ids": ["main"],
                "lora_selections": [
                    {"id": "L_no", "label": "No LoRA", "loras": [], "enabled": True},
                ],
            }],
        }],
        "prompts": {"items": [
            {"id": "p_a", "label": "a", "text": "hello", "negative": None, "enabled": True},
        ]},
        "variable_modes": {
            "prompt": {"mode": "independent", "enabled": True},
            "seed": {"mode": "sweep", "enabled": True},
        },
        "tested_values": {
            "seed": [42],
        },
        "controlled_values": {},
        "compatibility_mode": "standard",
        "advanced_execution": {
            "execution_mode": "sequential",
            "max_parallel": 1,
        },
        "axes": {"shared": {"seed": {"mode": "list", "values": [42]}}},
    }
    if overrides:
        draft.update(overrides)
    return draft


# ═══════════════════════════════════════════════════════════════════════
# 10. Normalised draft → compiler spec (rich fields passthrough)
# ═══════════════════════════════════════════════════════════════════════

class RichDraftTranslationTests(unittest.TestCase):
    """``normalized_draft_to_compiler_spec`` must pass through rich schema
    fields when they exist."""

    def test_generation_type_preserved(self):
        adapter = load_setup_adapter()
        draft = _minimal_rich_draft(overrides={"generation_type": "img2img"})
        spec = adapter.normalized_draft_to_compiler_spec(draft)
        self.assertEqual(spec.get("generation_type"), "img2img")

    def test_prompt_image_pairing_preserved(self):
        adapter = load_setup_adapter()
        draft = _minimal_rich_draft(overrides={"prompt_image_pairing": "paired"})
        spec = adapter.normalized_draft_to_compiler_spec(draft)
        self.assertEqual(spec.get("prompt_image_pairing"), "paired")

    def test_variable_modes_preserved(self):
        adapter = load_setup_adapter()
        draft = _minimal_rich_draft()
        spec = adapter.normalized_draft_to_compiler_spec(draft)
        self.assertIn("variable_modes", spec)

    def test_tested_values_preserved(self):
        adapter = load_setup_adapter()
        draft = _minimal_rich_draft()
        spec = adapter.normalized_draft_to_compiler_spec(draft)
        self.assertIn("tested_values", spec)

    def test_controlled_values_preserved(self):
        adapter = load_setup_adapter()
        draft = _minimal_rich_draft()
        spec = adapter.normalized_draft_to_compiler_spec(draft)
        self.assertIn("controlled_values", spec)

    def test_compatibility_mode_preserved(self):
        adapter = load_setup_adapter()
        draft = _minimal_rich_draft(overrides={"compatibility_mode": "strict"})
        spec = adapter.normalized_draft_to_compiler_spec(draft)
        self.assertEqual(spec.get("compatibility_mode"), "strict")

    def test_advanced_execution_preserved(self):
        adapter = load_setup_adapter()
        draft = _minimal_rich_draft()
        spec = adapter.normalized_draft_to_compiler_spec(draft)
        self.assertIn("advanced_execution", spec)


if __name__ == "__main__":
    unittest.main()
