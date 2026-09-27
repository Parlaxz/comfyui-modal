import importlib.util
import json
import sys
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = REPO_ROOT / "experiment_models.py"


def load_module():
    if not MODULE_PATH.exists():
        raise AssertionError("experiment_models.py missing")
    spec = importlib.util.spec_from_file_location("experiment_models", MODULE_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    # Register in sys.modules so dataclasses can resolve type annotations
    # (PEP 563 string annotations + importlib dynamic loading require this)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class CanonicalSerializerTests(unittest.TestCase):
    def test_canonical_dump_is_key_sorted(self):
        module = load_module()
        out = module.canonical_dump({"b": 1, "a": 2})
        self.assertEqual(out, '{"a":2,"b":1}')

    def test_canonical_dump_rejects_unknown_types(self):
        module = load_module()
        with self.assertRaises(TypeError):
            module.canonical_dump({"x": object()})

    def test_canonical_hash_is_stable_across_key_order(self):
        module = load_module()
        h1 = module.canonical_hash({"a": 1, "b": 2})
        h2 = module.canonical_hash({"b": 2, "a": 1})
        self.assertEqual(h1, h2)

    def test_canonical_hash_changes_with_value(self):
        module = load_module()
        self.assertNotEqual(
            module.canonical_hash({"a": 1}),
            module.canonical_hash({"a": 2}),
        )


class ExperimentDefinitionSchemaTests(unittest.TestCase):
    def test_minimal_definition_round_trip(self):
        module = load_module()
        d = module.ExperimentDefinition(
            schema_version=1,
            experiment_id="exp_abc",
            revision=1,
            name="Test",
            notes="",
            created_at="2026-06-17T12:00:00Z",
            updated_at="2026-06-17T12:00:00Z",
        )
        as_dict = module.definition_to_dict(d)
        restored = module.definition_from_dict(as_dict)
        self.assertEqual(d, restored)

    def test_definition_validator_rejects_bad_version(self):
        module = load_module()
        d = module.ExperimentDefinition(
            schema_version=99, experiment_id="x", revision=1,
            name="", notes="", created_at="", updated_at="",
        )
        with self.assertRaises(module.SchemaError):
            module.validate_definition(d)

    def test_definition_validator_rejects_empty_experiment_id(self):
        module = load_module()
        d = module.ExperimentDefinition(
            schema_version=1, experiment_id="", revision=1,
            name="", notes="", created_at="", updated_at="",
        )
        with self.assertRaises(module.SchemaError):
            module.validate_definition(d)


class CellKeySchemaTests(unittest.TestCase):
    def test_cell_key_round_trip(self):
        module = load_module()
        k = module.CellKey(
            experiment_id="exp_1",
            profile_id="p_1",
            loader_target_group_id="g_default",
            unet="u1", clip="c1", vae="v1",
            lora_signature=(("a.safetensors", 0.7, 0.7),),
            prompt_text="hello",
            negative_prompt_text="",
            input_image_hash="",
            seed=42, steps=20, guidance=3.5,
            sampler="euler", scheduler="normal", denoise=1.0,
            width=1024, height=1024,
        )
        d = module.cell_key_to_dict(k)
        restored = module.cell_key_from_dict(d)
        self.assertEqual(k, restored)

    def test_cell_key_hash_is_stable(self):
        module = load_module()
        k = module.CellKey(
            experiment_id="exp_1",
            profile_id="p_1",
            loader_target_group_id="g_default",
            unet="u1", clip="c1", vae="v1",
            lora_signature=(("a.safetensors", 0.7, 0.7),),
            prompt_text="hello",
            negative_prompt_text="",
            input_image_hash="",
            seed=42, steps=20, guidance=3.5,
            sampler="euler", scheduler="normal", denoise=1.0,
            width=1024, height=1024,
        )
        h1 = module.canonical_hash(module.cell_key_to_dict(k))
        h2 = module.canonical_hash(module.cell_key_to_dict(k))
        self.assertEqual(h1, h2)

    def test_cell_key_hash_changes_with_seed(self):
        module = load_module()
        base = dict(
            experiment_id="exp_1", profile_id="p_1",
            loader_target_group_id="g_default",
            unet="u1", clip="c1", vae="v1",
            lora_signature=(("a.safetensors", 0.7, 0.7),),
            prompt_text="hello", negative_prompt_text="",
            input_image_hash="", steps=20, guidance=3.5,
            sampler="euler", scheduler="normal", denoise=1.0,
            width=1024, height=1024,
        )
        k1 = module.CellKey(seed=1, **base)
        k2 = module.CellKey(seed=2, **base)
        self.assertNotEqual(
            module.canonical_hash(module.cell_key_to_dict(k1)),
            module.canonical_hash(module.cell_key_to_dict(k2)),
        )


class MigrationTests(unittest.TestCase):
    def test_migrate_v0_to_v1(self):
        module = load_module()
        legacy = {"experiment_id": "exp_x", "name": "legacy"}
        migrated = module.migrate(legacy, from_version=0, to_version=1)
        self.assertEqual(migrated["schema_version"], 1)
        self.assertEqual(migrated["experiment_id"], "exp_x")
        self.assertEqual(migrated["revision"], 1)

    def test_migrate_unknown_version_raises(self):
        module = load_module()
        with self.assertRaises(module.MigrationError):
            module.migrate({}, from_version=5, to_version=1)


if __name__ == "__main__":
    unittest.main()
