"""Unit tests for the legacy-preset to workflow adapters (abs-1).

Covers the exact adapter surface in ``studio_domain.legacy_adapters``:

* role translation (old → canonical renames: steps→step_count,
  cfg→cfg_scale, positive_prompt→prompt, model→model_unet, plus
  guidance→cfg_scale and unet→model_unet);
* unknown-role passthrough (untouched AND visible via ``unmapped_roles``);
* the run-contract resolution (``resolve_legacy_run_context`` +
  ``prepare_legacy_run_controls`` against a real mapped version, resolved
  through the verified ``resolve_workflow_run_bundle`` /
  ``merge_workflow_controls`` foundation — no rewrite, no migration).

Pure tests never touch the store; the run-contract tests use a temporary
WorkflowDomainStore root (the single durable authority).
"""

from __future__ import annotations

import copy
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from studio_domain.legacy_adapters import (
    CANONICAL_KEYS,
    LEGACY_ROLE_MAP,
    canonical_role,
    resolve_legacy_run_context,
    translate_legacy_preset,
    translate_model_choices,
    translate_values,
    unmapped_roles,
)
from studio_domain.services import WorkflowDomainService
from studio_run_adapter import translate_legacy_controls_for_workflow
from studio_workflow_run import (
    merge_workflow_controls,
    prepare_legacy_run_controls,
    resolve_workflow_run_bundle,
)


LEGACY_VALUES = {
    "positive_prompt": "a portrait",
    "seed": 7,
    "steps": 20,
    "cfg": 7.5,
    "sampler": "euler",
    "model": "krea_model.safetensors",
}


def txt2img_prompt() -> dict:
    return {
        "1": {"class_type": "CLIPTextEncode",
              "inputs": {"text": "hello world", "clip": ["4", 0]}},
        "2": {"class_type": "CLIPTextEncode",
              "inputs": {"text": "negative", "clip": ["4", 0]}},
        "3": {"class_type": "KSampler", "inputs": {
            "model": ["4", 0], "seed": 0, "steps": 20, "cfg": 7.0,
            "sampler_name": "euler", "scheduler": "normal",
            "positive": ["1", 0], "negative": ["2", 0],
            "latent_image": ["5", 0], "denoise": 1.0}},
        "4": {"class_type": "CheckpointLoaderSimple",
              "inputs": {"ckpt_name": "krea_model.safetensors"}},
        "5": {"class_type": "EmptyLatentImage",
              "inputs": {"width": 512, "height": 512, "batch_size": 1}},
        "6": {"class_type": "SaveImage", "inputs": {"images": ["3", 0]}},
    }


def canonical_mapping_entries() -> dict:
    """Mapping entries keyed by CANONICAL roles over the txt2img prompt."""
    def entry(node_id: str, input_name: str, **extra: Any) -> dict:
        base: dict[str, Any] = {"node_id": node_id, "input_name": input_name,
                "kind": "node_input", "control_kind": "string"}
        base.update(extra)
        return base

    return {
        "prompt": entry("1", "text", control_kind="multiline"),
        "seed": entry("3", "seed", control_kind="integer", minimum=0.0),
        "step_count": entry("3", "steps", control_kind="integer", minimum=1.0),
        "cfg_scale": entry("3", "cfg", control_kind="number", minimum=0.0),
        "sampler": entry("3", "sampler_name"),
        "model_unet": entry("4", "ckpt_name"),
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


class TranslateLegacyPresetTests(unittest.TestCase):
    def test_full_translation(self):
        legacy = {"label": "My Preset", "description": "d",
                  "values": dict(LEGACY_VALUES),
                  "model_choices": {"model": "krea_model.safetensors"}}
        out = translate_legacy_preset(legacy)
        self.assertEqual(out["name"], "My Preset")
        self.assertEqual(out["description"], "d")
        self.assertEqual(out["values"]["prompt"], "a portrait")
        self.assertEqual(out["values"]["step_count"], 20)
        self.assertEqual(out["values"]["cfg_scale"], 7.5)
        self.assertEqual(out["model_choices"],
                         {"model_unet": "krea_model.safetensors"})
        self.assertEqual(out["unmapped_roles"], [])
        self.assertEqual(out["role_collisions"], {})
        # Nothing dropped or invented: every input key lands canonically.
        self.assertEqual(set(out["values"]),
                         {canonical_role(k) for k in LEGACY_VALUES})

    def test_name_prefers_name_over_label(self):
        out = translate_legacy_preset({"name": "N", "label": "L",
                                       "values": {}})
        self.assertEqual(out["name"], "N")

    def test_empty_name_passes_through_for_truthful_validation(self):
        out = translate_legacy_preset({"values": {}})
        self.assertEqual(out["name"], "")

    def test_unknown_visible_and_collisions_visible(self):
        legacy = {"name": "P",
                  "values": {"steps": 20, "step_count": 30,
                             "custom_knob": 1},
                  "model_choices": {}}
        out = translate_legacy_preset(legacy)
        self.assertEqual(out["unmapped_roles"], ["custom_knob"])
        self.assertIn("custom_knob", out["values"])  # untouched, present
        self.assertEqual(out["role_collisions"],
                         {"step_count": ["step_count", "steps"]})


class ResolveLegacyRunContextTests(unittest.TestCase):
    def test_scope_and_override_merge(self):
        before = copy.deepcopy(LEGACY_VALUES)
        ctx = resolve_legacy_run_context(
            {"name": "P", "values": dict(LEGACY_VALUES),
             "model_choices": {"model": "krea_model.safetensors"}},
            workflow_id="wf_1",
            workflow_version_id="wv_1",
            overrides={"steps": 30, "custom_knob": 9},
            preset_id="wpres_1",
        )
        self.assertEqual(ctx["workflow_id"], "wf_1")
        self.assertEqual(ctx["workflow_version_id"], "wv_1")
        self.assertEqual(ctx["preset_id"], "wpres_1")
        # Overrides win per canonical key, translated before merging.
        self.assertEqual(ctx["values"]["step_count"], 30)
        self.assertEqual(ctx["values"]["prompt"], "a portrait")
        self.assertEqual(ctx["values"]["custom_knob"], 9)
        self.assertEqual(ctx["model_choices"],
                         {"model_unet": "krea_model.safetensors"})
        self.assertEqual(ctx["unmapped_roles"], ["custom_knob"])
        # Pure: caller inputs never mutated.
        self.assertEqual(LEGACY_VALUES, before)

    def test_run_contract_feeds_verified_merge(self):
        ctx = resolve_legacy_run_context(
            {"values": dict(LEGACY_VALUES)},
            workflow_id="wf_1", workflow_version_id="wv_1",
        )
        merged = merge_workflow_controls(
            {"values": {}, "model_choices": {}},
            ctx["values"],
            {role: {} for role in ctx["values"]},
        )
        self.assertEqual(merged["errors"], [])
        self.assertEqual(merged["values"]["step_count"], 20)


class LegacyBridgeTests(unittest.TestCase):
    def test_studio_run_adapter_bridge_is_pure_translation(self):
        controls = {"steps": 20, "cfg": 7.5, "positive_prompt": "hi",
                    "custom": 1}
        out = translate_legacy_controls_for_workflow(controls)
        self.assertEqual(out, {"step_count": 20, "cfg_scale": 7.5,
                               "prompt": "hi", "custom": 1})
        self.assertEqual(controls["steps"], 20)  # input untouched
        self.assertEqual(translate_legacy_controls_for_workflow(None), {})


class RunContractIntegrationTests(unittest.TestCase):
    """End-to-end run-contract resolution against the single authority."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.service = WorkflowDomainService(str(Path(self._tmp.name)))

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _setup_canonical_version(self) -> tuple[str, str, str]:
        wf = self.service.create_workflow("Legacy Absorb")
        capture = {"graph_json": {"id": "g1"},
                   "api_prompt_json": {"workflow": {},
                                       "output": txt2img_prompt()}}
        version = self.service.create_version_from_capture(
            wf["workflow_id"], capture)
        version_id = version["workflow_version_id"]
        self.service.set_mapping(version_id,
                                 entries=canonical_mapping_entries(),
                                 output_node_id="6")
        return wf["workflow_id"], version_id, self.service.store.root.as_posix()

    def _bundle(self, workflow_id: str, version_id: str,
                preset_id: str, root: str) -> dict:
        """Resolve through the verified bundle path with a resolver-free
        service (house pattern: no dependency resolver → deterministic
        runnable states headless)."""
        import studio_workflow_run as swr

        with mock.patch.object(
            swr, "_get_domain_service",
            new=lambda node_dir: WorkflowDomainService(str(node_dir)),
        ):
            return resolve_workflow_run_bundle(
                workflow_id, version_id, preset_id, root)

    def test_preset_from_legacy_then_bundle_then_controls(self):
        workflow_id, version_id, root = self._setup_canonical_version()
        preset = self.service.create_preset_from_legacy(
            version_id,
            {"label": "Legacy P", "values": dict(LEGACY_VALUES),
             "model_choices": {"model": "krea_model.safetensors"}})
        # Version-scoped, canonical keys, runnable — single authority.
        self.assertEqual(preset["workflow_version_id"], version_id)
        self.assertEqual(preset["values"]["prompt"], "a portrait")
        self.assertEqual(preset["values"]["step_count"], 20)
        self.assertNotIn("steps", preset["values"])
        self.assertEqual(preset["state"]["status"], "ready")

        bundle = self._bundle(workflow_id, version_id, preset["preset_id"], root)
        self.assertEqual(bundle["status"], "ok")

        merged = prepare_legacy_run_controls(
            bundle["control_schema"],
            {"values": dict(LEGACY_VALUES)}, {"steps": 25})
        self.assertEqual(merged["errors"], [])
        self.assertEqual(merged["values"]["step_count"], 25)
        self.assertEqual(merged["values"]["prompt"], "a portrait")
        self.assertEqual(merged["values"]["model_unet"],
                         "krea_model.safetensors")

    def test_unknown_control_errors_visibly_never_silently_dropped(self):
        _workflow_id, version_id, root = self._setup_canonical_version()
        bundle = self._bundle(_workflow_id, version_id, "", root)
        # No preset yet → bundle reports NO_PRESET (contract holds).
        self.assertEqual(bundle["status"], "error")
        self.assertEqual(bundle["error_code"], "NO_PRESET")

        preset = self.service.create_preset_from_legacy(
            version_id, {"name": "P", "values": dict(LEGACY_VALUES)})
        bundle = self._bundle(
            preset["workflow_id"], version_id, preset["preset_id"], root)
        merged = prepare_legacy_run_controls(
            bundle["control_schema"],
            {"values": dict(LEGACY_VALUES)},
            {"totally_unknown": 1})
        self.assertTrue(any(e["field"] == "totally_unknown"
                            for e in merged["errors"]))


if __name__ == "__main__":
    unittest.main()
