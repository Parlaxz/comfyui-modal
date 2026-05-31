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


class WarmupWorkflowReplayTests(unittest.TestCase):
    """Tests for replaying the actual successful workflow as warmup."""

    def test_replay_warmup_preserves_loader_options_and_reduces_steps(self):
        from comfyapp import build_replay_warmup_workflow

        workflow = {
            "1": {"class_type": "UNETLoader", "inputs": {"unet_name": "flux.safetensors", "weight_dtype": "fp8_e4m3fn"}},
            "2": {"class_type": "DualCLIPLoader", "inputs": {"clip_name1": "clip_l.safetensors", "clip_name2": "t5xxl.safetensors", "type": "flux"}},
            "3": {"class_type": "VAELoader", "inputs": {"vae_name": "vae.safetensors"}},
            "4": {"class_type": "ModelSamplingFlux", "inputs": {"model": ["1", 0], "max_shift": 1.25, "base_shift": 0.4, "width": 1344, "height": 768}},
            "5": {"class_type": "EmptyLatentImage", "inputs": {"width": 1344, "height": 768, "batch_size": 1}},
            "6": {"class_type": "KSampler", "inputs": {"seed": 42, "steps": 30, "cfg": 3.5, "sampler_name": "euler", "scheduler": "normal", "denoise": 1.0, "model": ["4", 0], "positive": ["2", 0], "negative": ["2", 0], "latent_image": ["5", 0]}},
            "7": {"class_type": "SaveImage", "inputs": {"filename_prefix": "real", "images": ["6", 0]}},
        }

        warmup = build_replay_warmup_workflow(workflow)

        self.assertEqual(warmup["2"]["inputs"], workflow["2"]["inputs"])
        self.assertEqual(warmup["1"]["inputs"]["weight_dtype"], "fp8_e4m3fn")
        self.assertEqual(warmup["4"]["inputs"]["max_shift"], 1.25)
        self.assertEqual(warmup["6"]["inputs"]["steps"], 1)
        self.assertEqual(warmup["5"]["inputs"]["width"], 512)
        self.assertEqual(warmup["5"]["inputs"]["height"], 512)
        self.assertEqual(warmup["7"]["inputs"]["filename_prefix"], "warmup")

    def test_replay_warmup_reduces_custom_sampler_numeric_steps(self):
        from comfyapp import build_replay_warmup_workflow

        workflow = {
            "10": {"class_type": "PowerSampler", "inputs": {"steps": 20, "end_at_step": 20, "start_at_step": 3}},
            "11": {"class_type": "OtherSampler", "inputs": {"num_steps": "30", "width": 1024, "height": 768}},
        }

        warmup = build_replay_warmup_workflow(workflow)

        self.assertEqual(warmup["10"]["inputs"]["steps"], 1)
        self.assertEqual(warmup["10"]["inputs"]["end_at_step"], 1)
        self.assertEqual(warmup["10"]["inputs"]["start_at_step"], 0)
        self.assertEqual(warmup["11"]["inputs"]["num_steps"], 1)
        self.assertEqual(warmup["11"]["inputs"]["width"], 512)
        self.assertEqual(warmup["11"]["inputs"]["height"], 512)

    def test_flux_clip_order_normalizes_known_reversed_names(self):
        from comfyapp import normalize_flux_clip_pair

        self.assertEqual(
            normalize_flux_clip_pair("t5xxl_fp16.safetensors", "clip_l.safetensors"),
            ("clip_l.safetensors", "t5xxl_fp16.safetensors"),
        )


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


class ModelCpuCachePatchTests(unittest.TestCase):
    def _make_instance(self):
        from comfyapp import _ComfyAPIMixin
        inst = object.__new__(_ComfyAPIMixin)
        inst._model_cpu_cache = {"demo.safetensors": {"tensor": 1}}
        return inst

    def test_cache_hit_preserves_return_metadata_contract(self):
        inst = self._make_instance()

        class FakeComfyUtils:
            def load_torch_file(self, path, *args, **kwargs):
                raise AssertionError("cache hit should not call original loader")

        fake_utils = FakeComfyUtils()
        inst._patch_model_cpu_cache(fake_utils)

        result = fake_utils.load_torch_file("/tmp/demo.safetensors", return_metadata=True)
        self.assertEqual(result, ({"tensor": 1}, None))

    def test_cache_hit_returns_state_dict_only_without_metadata_flag(self):
        inst = self._make_instance()

        class FakeComfyUtils:
            def load_torch_file(self, path, *args, **kwargs):
                raise AssertionError("cache hit should not call original loader")

        fake_utils = FakeComfyUtils()
        inst._patch_model_cpu_cache(fake_utils)

        result = fake_utils.load_torch_file("/tmp/demo.safetensors")
        self.assertEqual(result, {"tensor": 1})

    def test_cache_hit_uses_cached_metadata_tuple_when_available(self):
        from comfyapp import _ComfyAPIMixin

        inst = object.__new__(_ComfyAPIMixin)
        inst._model_cpu_cache = {"demo.safetensors": ({"tensor": 1}, {"format": "fp8"})}

        class FakeComfyUtils:
            def load_torch_file(self, path, *args, **kwargs):
                raise AssertionError("cache hit should not call original loader")

        fake_utils = FakeComfyUtils()
        inst._patch_model_cpu_cache(fake_utils)

        self.assertEqual(
            fake_utils.load_torch_file("/tmp/demo.safetensors", return_metadata=True),
            ({"tensor": 1}, {"format": "fp8"}),
        )
        self.assertEqual(fake_utils.load_torch_file("/tmp/demo.safetensors"), {"tensor": 1})

    def test_cache_hit_returns_shallow_copy(self):
        """Cache hit returns a dict-level copy; nested mutables are shared.

        This is intentional: state dicts contain torch tensors which are
        effectively immutable for in-place operations during model loading.
        Avoiding deepcopy saves ~4s on a 17 GB Flux+Qwen model stack.
        """
        from comfyapp import _ComfyAPIMixin

        inst = object.__new__(_ComfyAPIMixin)
        inst._model_cpu_cache = {"demo.safetensors": ({"tensor": [1, 2]}, {"format": {"kind": "fp8"}})}

        class FakeComfyUtils:
            def load_torch_file(self, path, *args, **kwargs):
                raise AssertionError("cache hit should not call original loader")

        fake_utils = FakeComfyUtils()
        inst._patch_model_cpu_cache(fake_utils)

        # Verify we get a *dict* copy (top-level key add doesn't affect cache)
        state_dict, metadata = fake_utils.load_torch_file("/tmp/demo.safetensors", return_metadata=True)
        state_dict["new_key"] = "added"
        cached_state, cached_metadata = inst._model_cpu_cache["demo.safetensors"]
        self.assertNotIn("new_key", cached_state)

        # Verify nested mutables ARE shared (shallow copy, not deep copy)
        self.assertIs(state_dict["tensor"], cached_state["tensor"])
        self.assertIs(metadata["format"], cached_metadata["format"])


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

    def test_restore_logs_warmup_cuda_warmup_for_in_process(self):
        source = self._get_method_source("restore")
        self.assertIsNotNone(source)
        self.assertIn("restore_warmup", source)
        self.assertIn("cuda_warmup", source)

    def test_run_prompt_calls_save_last_model_stack(self):
        source = self._get_method_source("run_prompt")
        self.assertIsNotNone(source)
        self.assertIn("_save_last_model_stack", source)

    def test_preload_warmup_profile_falls_back_to_stack_to_profile(self):
        source = self._get_method_source("_preload_warmup_profile")
        self.assertIsNotNone(source)
        self.assertIn("stack_to_profile", source)
        self.assertIn("_load_last_model_stack", source)

    def test_module_exports_stack_to_profile(self):
        source = COMFYAPP_PATH.read_text(encoding="utf-8")
        self.assertIn("def stack_to_profile", source)


if __name__ == "__main__":
    unittest.main()
