"""Unit tests for the legacy control-role translation adapters.

Covers the live surface in ``studio_domain.legacy_adapters``, which exists to
translate the OLD Studio control role names still emitted by the legacy
canvas/prompt path into the CANONICAL bindable-input keys:

* role translation (old → canonical renames: steps→step_count, cfg→cfg_scale,
  positive_prompt→prompt, model→model_unet, plus guidance→cfg_scale and
  unet→model_unet);
* unknown-role passthrough (untouched AND visible via ``unmapped_roles``);
* purity — inputs are never mutated.

These are pure tests; they never touch the store.
"""

from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from studio_domain.legacy_adapters import (
    CANONICAL_KEYS,
    LEGACY_ROLE_MAP,
    canonical_role,
    translate_model_choices,
    translate_values,
    unmapped_roles,
)
from studio_run_adapter import translate_legacy_controls_for_workflow


LEGACY_VALUES = {
    "positive_prompt": "a portrait",
    "seed": 7,
    "steps": 20,
    "cfg": 7.5,
    "sampler": "euler",
    "model": "krea_model.safetensors",
}


class CanonicalRoleTests(unittest.TestCase):
    def test_old_to_canonical_renames(self):
        self.assertEqual(canonical_role("positive_prompt"), "prompt")
        self.assertEqual(canonical_role("steps"), "step_count")
        self.assertEqual(canonical_role("cfg"), "cfg_scale")
        self.assertEqual(canonical_role("guidance"), "cfg_scale")
        self.assertEqual(canonical_role("model"), "model_unet")
        self.assertEqual(canonical_role("unet"), "model_unet")

    def test_canonical_keys_are_identity(self):
        for key in ("prompt", "seed", "step_count", "cfg_scale",
                    "sampler", "model_unet", "vae", "clip"):
            self.assertEqual(canonical_role(key), key)
        self.assertEqual(set(LEGACY_ROLE_MAP.values()) | {
            "seed", "sampler", "prompt", "vae", "clip",
        }, set(CANONICAL_KEYS))

    def test_unknown_roles_untouched(self):
        self.assertEqual(canonical_role("negative_prompt"), "negative_prompt")
        self.assertEqual(canonical_role("mask_blur"), "mask_blur")
        self.assertEqual(canonical_role(""), "")


class TranslateValuesTests(unittest.TestCase):
    def test_renames_keys_preserves_values(self):
        before = copy.deepcopy(LEGACY_VALUES)
        out = translate_values(LEGACY_VALUES)
        self.assertEqual(out, {
            "prompt": "a portrait",
            "seed": 7,
            "step_count": 20,
            "cfg_scale": 7.5,
            "sampler": "euler",
            "model_unet": "krea_model.safetensors",
        })
        # Pure: input never mutated.
        self.assertEqual(LEGACY_VALUES, before)

    def test_falsy_values_survive(self):
        out = translate_values({"seed": 0, "steps": 0, "cfg": 0.0,
                                "positive_prompt": "", "sampler": "euler"})
        self.assertEqual(out["seed"], 0)
        self.assertEqual(out["step_count"], 0)
        self.assertEqual(out["cfg_scale"], 0.0)
        self.assertEqual(out["prompt"], "")

    def test_unknown_role_passthrough(self):
        out = translate_values({"steps": 20, "mask_blur": 3,
                                "lora_strength": 0.5})
        self.assertEqual(out["step_count"], 20)
        self.assertEqual(out["mask_blur"], 3)
        self.assertEqual(out["lora_strength"], 0.5)

    def test_none_and_empty(self):
        self.assertEqual(translate_values(None), {})
        self.assertEqual(translate_values({}), {})
        self.assertEqual(translate_model_choices(None), {})

    def test_model_choices_rename(self):
        out = translate_model_choices({"model": "krea_model.safetensors",
                                       "vae": "vae.safetensors"})
        self.assertEqual(out, {"model_unet": "krea_model.safetensors",
                               "vae": "vae.safetensors"})


class UnmappedRolesTests(unittest.TestCase):
    def test_known_roles_not_reported(self):
        self.assertEqual(unmapped_roles(dict(LEGACY_VALUES)), [])
        self.assertEqual(unmapped_roles({"prompt": "x", "vae": "v",
                                         "clip": "c", "seed": 1}), [])

    def test_unknown_roles_visible_sorted(self):
        self.assertEqual(
            unmapped_roles({"steps": 1, "mask_blur": 2, "lora_strength": 3},
                           {"model": "m", "weird": "w"}),
            ["lora_strength", "mask_blur", "weird"],
        )


class LegacyBridgeTests(unittest.TestCase):
    def test_studio_run_adapter_bridge_is_pure_translation(self):
        controls = {"steps": 20, "cfg": 7.5, "positive_prompt": "hi",
                    "custom": 1}
        out = translate_legacy_controls_for_workflow(controls)
        self.assertEqual(out, {"step_count": 20, "cfg_scale": 7.5,
                               "prompt": "hi", "custom": 1})
        self.assertEqual(controls["steps"], 20)  # input untouched
        self.assertEqual(translate_legacy_controls_for_workflow(None), {})


if __name__ == "__main__":
    unittest.main()