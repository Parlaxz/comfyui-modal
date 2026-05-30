import ast
import json
import os
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
COMFYAPP_PATH = REPO_ROOT / "comfyapp.py"


class StackToProfileTests(unittest.TestCase):
    """Test the stack_to_profile conversion function."""

    def test_checkpoint_mode(self):
        from comfyapp import stack_to_profile
        stack = {"checkpoint": ["sd_xl_base.safetensors"], "unet": [], "clip": [], "vae": []}
        self.assertEqual(stack_to_profile(stack), {"mode": "checkpoint", "checkpoint": "sd_xl_base.safetensors"})

    def test_checkpoint_first_entry_used(self):
        from comfyapp import stack_to_profile
        stack = {"checkpoint": ["first.sft", "second.sft"], "unet": [], "clip": [], "vae": []}
        self.assertEqual(stack_to_profile(stack), {"mode": "checkpoint", "checkpoint": "first.sft"})

    def test_split_mode_with_two_clips(self):
        from comfyapp import stack_to_profile
        stack = {
            "checkpoint": [],
            "unet": ["flux-2-klein-9b-fp8.safetensors"],
            "clip": ["clip_l.safetensors", "t5xxl.safetensors"],
            "vae": ["vae.safetensors"],
        }
        self.assertEqual(stack_to_profile(stack), {
            "mode": "split",
            "unet": "flux-2-klein-9b-fp8.safetensors",
            "clip1": "clip_l.safetensors",
            "clip2": "t5xxl.safetensors",
            "vae": "vae.safetensors",
            "clip_type": "flux",
        })

    def test_split_mode_with_single_clip(self):
        from comfyapp import stack_to_profile
        stack = {
            "checkpoint": [],
            "unet": ["flux.safetensors"],
            "clip": ["single_clip.safetensors"],
            "vae": ["vae.safetensors"],
        }
        self.assertEqual(stack_to_profile(stack), {
            "mode": "split",
            "unet": "flux.safetensors",
            "clip1": "single_clip.safetensors",
            "clip2": "single_clip.safetensors",
            "vae": "vae.safetensors",
            "clip_type": "flux",
        })

    def test_empty_stack_returns_empty_dict(self):
        from comfyapp import stack_to_profile
        self.assertEqual(stack_to_profile({"checkpoint": [], "unet": [], "clip": [], "vae": []}), {})

    def test_partial_split_returns_empty(self):
        from comfyapp import stack_to_profile
        self.assertEqual(stack_to_profile({"checkpoint": [], "unet": ["u.sft"], "clip": [], "vae": []}), {})

    def test_checkpoint_takes_priority_over_split(self):
        from comfyapp import stack_to_profile
        stack = {
            "checkpoint": ["ckpt.sft"],
            "unet": ["u.sft"],
            "clip": ["c.sft"],
            "vae": ["v.sft"],
        }
        self.assertEqual(stack_to_profile(stack), {"mode": "checkpoint", "checkpoint": "ckpt.sft"})


class SaveLoadStackTests(unittest.TestCase):
    """Test _save_last_model_stack and _load_last_model_stack via temp file."""

    def setUp(self):
        self.tmp = tempfile.mktemp(suffix=".json")
        import comfyapp
        comfyapp.LAST_MODEL_STACK_PATH = self.tmp

    def tearDown(self):
        if os.path.isfile(self.tmp):
            os.remove(self.tmp)

    def _make_instance(self):
        from comfyapp import _ComfyAPIMixin
        instance = object.__new__(_ComfyAPIMixin)
        return instance

    def test_save_and_load_roundtrip(self):
        inst = self._make_instance()
        stack = {"unet": ["flux.safetensors"], "clip": ["c1.sft", "c2.sft"], "vae": ["v.sft"], "checkpoint": []}
        inst._save_last_model_stack(stack)
        loaded = inst._load_last_model_stack()
        self.assertEqual(loaded, stack)

    def test_load_nonexistent_file_returns_empty(self):
        inst = self._make_instance()
        self.assertEqual(inst._load_last_model_stack(), {})

    def test_load_corrupted_json_returns_empty(self):
        inst = self._make_instance()
        with open(self.tmp, "w") as f:
            f.write("not valid json")
        self.assertEqual(inst._load_last_model_stack(), {})

    def test_save_empty_stack_does_not_crash(self):
        inst = self._make_instance()
        inst._save_last_model_stack({"checkpoint": [], "unet": [], "clip": [], "vae": []})

    def test_load_returns_copy_not_reference(self):
        inst = self._make_instance()
        stack = {"unet": ["u.sft"], "clip": ["c.sft"], "vae": ["v.sft"], "checkpoint": []}
        inst._save_last_model_stack(stack)
        loaded = inst._load_last_model_stack()
        loaded["unet"].append("extra")
        # Verify re-load gives original
        reloaded = inst._load_last_model_stack()
        self.assertEqual(reloaded["unet"], ["u.sft"])


class AutoWarmupASTTests(unittest.TestCase):
    """Structural tests via AST parsing (no Modal dependency)."""

    def _get_method_source(self, method_name: str) -> str | None:
        tree = ast.parse(COMFYAPP_PATH.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == method_name:
                return ast.get_source_segment(COMFYAPP_PATH.read_text(encoding="utf-8"), node)
        return None

    def test_restore_does_not_call_preload_warmup_profile(self):
        source = self._get_method_source("restore")
        self.assertIsNotNone(source, "restore method not found")
        self.assertNotIn("_preload_warmup_profile", source)

    def test_run_prompt_calls_save_last_model_stack(self):
        source = self._get_method_source("run_prompt")
        self.assertIsNotNone(source)
        self.assertIn("_save_last_model_stack", source)

    def test_preload_warmup_profile_falls_back_to_stack_to_profile(self):
        source = self._get_method_source("_preload_warmup_profile")
        self.assertIsNotNone(source)
        self.assertIn("stack_to_profile", source)
        self.assertIn("_load_last_model_stack", source)

    def test_preload_warmup_profile_tracks_source_field(self):
        source = self._get_method_source("_preload_warmup_profile")
        self.assertIsNotNone(source)
        self.assertIn('source = "pinned"', source)
        self.assertIn('source = "auto"', source)
        self.assertIn('"source": source', source)
        self.assertIn('"source": "none"', source)

    def test_startup_logs_source_field(self):
        source = self._get_method_source("startup")
        self.assertIsNotNone(source)
        self.assertIn("source=", source)

    def test_module_exports_stack_to_profile(self):
        source = COMFYAPP_PATH.read_text(encoding="utf-8")
        self.assertIn("def stack_to_profile", source)


if __name__ == "__main__":
    unittest.main()
