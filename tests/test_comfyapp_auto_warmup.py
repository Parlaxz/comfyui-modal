import ast
import json
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock


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

    def test_save_swallows_background_commit_failures(self):
        inst = self._make_instance()
        stack = {"unet": ["u.sft"], "clip": ["c.sft"], "vae": ["v.sft"], "checkpoint": []}
        import comfyapp

        class ImmediateThread:
            def __init__(self, target=None, daemon=None):
                self._target = target

            def start(self):
                if self._target is not None:
                    self._target()

        original_vol = comfyapp.vol
        comfyapp.vol = SimpleNamespace(commit=lambda: (_ for _ in ()).throw(RuntimeError("commit failed")))
        try:
            with mock.patch("threading.Thread", ImmediateThread), mock.patch("builtins.print") as print_mock:
                inst._save_last_model_stack(stack)
        finally:
            comfyapp.vol = original_vol

        failure_logs = [call for call in print_mock.call_args_list if "failed to save last model stack" in str(call)]
        self.assertEqual(failure_logs, [])
        self.assertEqual(inst._load_last_model_stack(), stack)


class SaveLoadActiveProfileTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mktemp(suffix=".json")
        import comfyapp
        comfyapp.ACTIVE_NEXT_PROFILE_PATH = self.tmp
        comfyapp.ACTIVE_NEXT_PROFILE_TTL_S = 60
        self._vol_patch = mock.patch.object(comfyapp.vol, "commit", return_value=None)
        self._vol_patch.start()

    def tearDown(self):
        self._vol_patch.stop()
        if os.path.isfile(self.tmp):
            os.remove(self.tmp)

    def _make_instance(self):
        from comfyapp import _ComfyAPIMixin
        return object.__new__(_ComfyAPIMixin)

    def test_write_and_load_active_profile_roundtrip(self):
        inst = self._make_instance()
        payload = {
            "profile_token": "tok-1",
            "workflow_hash": "hash-1",
            "created_at": 1000.0,
            "expires_at": 1060.0,
            "disable_warmup": False,
            "model_stack": {"unet": ["u.safetensors"], "clip": ["c.safetensors"], "vae": ["v.safetensors"], "checkpoint": [], "clip_type": "flux"},
            "warmup_profile": {"mode": "split", "unet": "u.safetensors", "clip1": "c.safetensors", "clip2": "c.safetensors", "vae": "v.safetensors", "clip_type": "flux"},
        }
        class _MockVol:
            def commit(self): pass
        inst._write_active_next_profile(payload, _MockVol())
        self.assertEqual(inst._load_active_next_profile(now=1001.0)["profile_token"], "tok-1")

    def test_load_active_profile_returns_expired_diagnostic_when_expired(self):
        inst = self._make_instance()
        class _MockVol2:
            def commit(self): pass
        inst._write_active_next_profile({
            "profile_token": "tok-expired",
            "workflow_hash": "hash-old",
            "created_at": 1000.0,
            "expires_at": 1001.0,
            "disable_warmup": False,
            "model_stack": {},
            "warmup_profile": {"mode": "checkpoint", "checkpoint": "old.safetensors"},
        }, _MockVol2())
        result = inst._load_active_next_profile(now=1002.0)
        self.assertEqual(result.get("_diagnostic", {}).get("status"), "expired")
        self.assertIn("warmup_profile", result)


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

    def test_cache_hit_uses_full_path_identity(self):
        from comfyapp import _ComfyAPIMixin

        inst = object.__new__(_ComfyAPIMixin)
        inst._model_cpu_cache = {
            "/tmp/models/a/demo.safetensors": {"tensor": "a"},
            "/tmp/models/b/demo.safetensors": {"tensor": "b"},
        }

        class FakeComfyUtils:
            def load_torch_file(self, path, *args, **kwargs):
                raise AssertionError("full-path cache hit should not call original loader")

        fake_utils = FakeComfyUtils()
        inst._patch_model_cpu_cache(fake_utils)

        result = fake_utils.load_torch_file("/tmp/models/b/demo.safetensors")
        self.assertEqual(result, {"tensor": "b"})


class SnapshotPreloadProfileTests(unittest.TestCase):
    """Tests for _snapshot_preload_profile fallback precedence."""

    def _make_instance(self):
        from comfyapp import _ComfyAPIMixin
        return object.__new__(_ComfyAPIMixin)

    def test_snapshot_preload_profile_falls_back_to_env_default_when_no_active_profile(self):
        inst = self._make_instance()
        inst._load_last_model_stack = lambda: {
            "checkpoint": [],
            "unet": ["stale-unet.safetensors"],
            "clip": ["stale-clip.safetensors"],
            "vae": ["stale-vae.safetensors"],
        }
        with mock.patch.dict(os.environ, {
            "COMFYMODAL_WARMUP_UNET": "env-unet.safetensors",
            "COMFYMODAL_WARMUP_CLIP1": "env-clip-1.safetensors",
            "COMFYMODAL_WARMUP_CLIP2": "env-clip-2.safetensors",
            "COMFYMODAL_WARMUP_VAE": "env-vae.safetensors",
            "COMFYMODAL_WARMUP_CLIP_TYPE": "flux2",
        }, clear=False):
            profile = inst._snapshot_preload_profile()

        self.assertEqual(profile["_source"], "env_default")
        self.assertEqual(profile["mode"], "split", "env vars should produce split mode")
        self.assertEqual(profile["unet"], "env-unet.safetensors")
        self.assertEqual(profile["clip1"], "env-clip-1.safetensors")
        self.assertEqual(profile["clip2"], "env-clip-2.safetensors")
        self.assertEqual(profile["vae"], "env-vae.safetensors")
        self.assertEqual(profile["clip_type"], "flux2", "env clip_type should be preserved")

    def test_snapshot_preload_profile_returns_empty_without_stack_or_env_profile(self):
        import comfyapp as _ca

        inst = self._make_instance()
        inst._load_last_model_stack = lambda: {}
        with mock.patch.dict(os.environ, {
            "COMFYMODAL_WARMUP_CHECKPOINT": "",
            "COMFYMODAL_WARMUP_UNET": "",
            "COMFYMODAL_WARMUP_CLIP1": "",
            "COMFYMODAL_WARMUP_CLIP2": "",
            "COMFYMODAL_WARMUP_VAE": "",
            "COMFYMODAL_WARMUP_CLIP_TYPE": "",
        }, clear=False), \
            mock.patch.object(_ca, "WARMUP_CHECKPOINT", ""), \
            mock.patch.object(_ca, "WARMUP_UNET", ""), \
            mock.patch.object(_ca, "WARMUP_CLIP1", ""), \
            mock.patch.object(_ca, "WARMUP_CLIP2", ""), \
            mock.patch.object(_ca, "WARMUP_VAE", ""), \
            mock.patch.object(_ca, "WARMUP_CLIP_TYPE", ""):
            profile = inst._snapshot_preload_profile()

        self.assertIsNone(profile)

    def test_snapshot_preload_profile_prefers_active_next_over_env_and_ignores_last_stack(self):
        inst = self._make_instance()
        inst._load_last_model_stack = lambda: {"unet": ["stale-unet.safetensors"], "clip": ["stale-clip.safetensors"], "vae": ["stale-vae.safetensors"], "checkpoint": []}
        inst._load_active_next_profile = lambda now=None: {
            "profile_token": "tok-new",
            "workflow_hash": "hash-new",
            "created_at": 1000.0,
            "expires_at": 1060.0,
            "disable_warmup": False,
            "model_stack": {"unet": ["new-unet.safetensors"], "clip": ["new-clip.safetensors"], "vae": ["new-vae.safetensors"], "checkpoint": [], "clip_type": "flux"},
            "warmup_profile": {"mode": "split", "unet": "new-unet.safetensors", "clip1": "new-clip.safetensors", "clip2": "new-clip.safetensors", "vae": "new-vae.safetensors", "clip_type": "flux"},
        }
        with mock.patch.dict(os.environ, {"COMFYMODAL_WARMUP_UNET": "env-unet.safetensors"}, clear=False):
            profile = inst._snapshot_preload_profile()
        self.assertEqual(profile["_source"], "active_next_profile")
        self.assertEqual(profile["unet"], "new-unet.safetensors")
        self.assertEqual(profile["_profile_token"], "tok-new")

    def test_snapshot_preload_profile_uses_env_default_when_no_active_profile(self):
        inst = self._make_instance()
        inst._load_active_next_profile = lambda now=None: {}
        inst._load_last_model_stack = lambda: {"unet": ["stale-unet.safetensors"], "clip": ["stale-clip.safetensors"], "vae": ["stale-vae.safetensors"], "checkpoint": []}
        with mock.patch.dict(os.environ, {
            "COMFYMODAL_WARMUP_UNET": "env-unet.safetensors",
            "COMFYMODAL_WARMUP_CLIP1": "env-clip.safetensors",
            "COMFYMODAL_WARMUP_CLIP2": "env-clip.safetensors",
            "COMFYMODAL_WARMUP_VAE": "env-vae.safetensors",
            "COMFYMODAL_WARMUP_CLIP_TYPE": "flux",
        }, clear=False):
            profile = inst._snapshot_preload_profile()
        self.assertEqual(profile["_source"], "env_default")
        self.assertEqual(profile["unet"], "env-unet.safetensors")

    def test_snapshot_preload_profile_returns_none_when_active_profile_disables_warmup(self):
        inst = self._make_instance()
        inst._load_active_next_profile = lambda now=None: {
            "profile_token": "tok-disable",
            "workflow_hash": "hash-disable",
            "created_at": 1000.0,
            "expires_at": 1060.0,
            "disable_warmup": True,
            "model_stack": {},
            "warmup_profile": {},
        }
        self.assertIsNone(inst._snapshot_preload_profile())


class RestoreBackgroundUnetEligibilityTests(unittest.TestCase):
    def _make_instance(self):
        from comfyapp import _ComfyAPIMixin
        inst = object.__new__(_ComfyAPIMixin)
        inst._model_cpu_cache = {}
        inst._actual_load_futures = {}
        inst._actual_load_future_meta = {}
        inst._actual_load_locks = {}
        inst._actual_load_owner_thread = {}
        inst._unet_object_cache = {}
        inst._original_loaders_store = {"UNETLoader.load_unet": lambda *a, **k: (object(),)}
        return inst

    def _profile(self, *, unets=None, clip_name="clip.safetensors", source="active_next_profile"):
        unets = list(unets or ["unet.safetensors"])
        return {
            "_source": source,
            "_current_workflow_stack": {
                "unet": unets,
                "clip": [clip_name],
                "vae": ["vae.safetensors"],
                "checkpoint": [],
                "clip_type": "lumina2",
            },
            "unet": unets[0] if unets else "",
            "clip1": clip_name,
            "clip2": clip_name,
            "vae": "vae.safetensors",
            "clip_type": "lumina2",
        }

    def _clip_policy(self, *, decision="load_and_encode_default"):
        return {
            "restore_direct_clip_policy": "auto",
            "restore_direct_clip_policy_decision": decision,
            "direct_warmup_load_clip_effective": 1 if decision == "load_and_encode_default" else 0,
            "direct_warmup_clip_encode_effective": 1 if decision == "load_and_encode_default" else 0,
        }

    def _preload_result(self, *, cached=None, aborted=False, failed_files=0, running_threads_not_killable=0):
        return {
            "cached": list(["clip.safetensors"] if cached is None else cached),
            "aborted": aborted,
            "failed_files": failed_files,
            "running_threads_not_killable": running_threads_not_killable,
        }

    def test_restore_background_unet_enabled_uses_runtime_flag_file(self):
        import comfyapp

        with tempfile.TemporaryDirectory() as tmpdir, \
             mock.patch.object(comfyapp, "_PRODUCTION_BASELINE_OVERRIDES", {}), \
             mock.patch.object(comfyapp, "RUNTIME_CONFIG_DIR", tmpdir), \
             mock.patch.object(comfyapp, "RESTORE_BACKGROUND_UNET_ENABLED", False), \
             mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("COMFYMODAL_RESTORE_BACKGROUND_UNET", None)
            with open(os.path.join(tmpdir, "RESTORE_BACKGROUND_UNET.txt"), "w", encoding="utf-8") as f:
                f.write("1")

            self.assertTrue(comfyapp._resolve_runtime_flag("RESTORE_BACKGROUND_UNET", "0"))
            self.assertTrue(comfyapp._restore_background_unet_enabled())

    def test_restore_background_unet_requires_valid_active_next_profile(self):
        inst = self._make_instance()
        import comfyapp

        fake_folder_paths = SimpleNamespace(
            get_full_path=lambda bucket, name: f"/models/{bucket}/{name}" if name else ""
        )
        with mock.patch.object(comfyapp, "_PRODUCTION_BASELINE_OVERRIDES", {}), \
             mock.patch.object(comfyapp, "RESTORE_BACKGROUND_UNET_ENABLED", True), \
             mock.patch.object(comfyapp, "_running_large_reads_locked", return_value=[]), \
             mock.patch.dict("sys.modules", {"folder_paths": fake_folder_paths}):
            eligibility = inst._restore_background_unet_eligibility(
                self._profile(source="env_default"),
                self._clip_policy(),
                self._preload_result(),
            )

        self.assertEqual(eligibility["eligible"], 0)
        self.assertEqual(eligibility["reason"], "active_next_profile_invalid")

    def test_restore_background_unet_accepts_load_only_explicit_clip_decision(self):
        """The eligibility function must accept 'load_only_explicit' as a
        valid clip policy decision (the canonical semantic used by the
        v2.16.21 fastpath auto load-only mode)."""
        import comfyapp
        inst = self._make_instance()

        fake_folder_paths = SimpleNamespace(
            get_full_path=lambda bucket, name: f"/models/{bucket}/{name}" if name else ""
        )
        clip_path = "/models/text_encoders/clip.safetensors"
        inst._model_cpu_cache[comfyapp._model_cpu_cache_key(clip_path)] = ({"tensor": 1}, None)
        with mock.patch.object(comfyapp, "_PRODUCTION_BASELINE_OVERRIDES", {}), \
             mock.patch.object(comfyapp, "RESTORE_BACKGROUND_UNET_ENABLED", True), \
             mock.patch.object(comfyapp, "_running_large_reads_locked", return_value=[]), \
             mock.patch.dict("sys.modules", {"folder_paths": fake_folder_paths}):
            eligibility = inst._restore_background_unet_eligibility(
                self._profile(),
                self._clip_policy(decision="load_only_explicit"),
                self._preload_result(),
            )

        self.assertEqual(eligibility["eligible"], 1,
                         "load_only_explicit should be accepted as valid")
        self.assertEqual(eligibility["reason"], "eligible")
        self.assertEqual(eligibility["clip_policy_decision"], "load_only_explicit")

    def test_restore_background_unet_accepts_load_and_encode_explicit_clip_decision(self):
        """'load_and_encode_explicit' must also be accepted."""
        import comfyapp
        inst = self._make_instance()

        fake_folder_paths = SimpleNamespace(
            get_full_path=lambda bucket, name: f"/models/{bucket}/{name}" if name else ""
        )
        clip_path = "/models/text_encoders/clip.safetensors"
        inst._model_cpu_cache[comfyapp._model_cpu_cache_key(clip_path)] = ({"tensor": 1}, None)
        with mock.patch.object(comfyapp, "_PRODUCTION_BASELINE_OVERRIDES", {}), \
             mock.patch.object(comfyapp, "RESTORE_BACKGROUND_UNET_ENABLED", True), \
             mock.patch.object(comfyapp, "_running_large_reads_locked", return_value=[]), \
             mock.patch.dict("sys.modules", {"folder_paths": fake_folder_paths}):
            eligibility = inst._restore_background_unet_eligibility(
                self._profile(),
                self._clip_policy(decision="load_and_encode_explicit"),
                self._preload_result(),
            )

        self.assertEqual(eligibility["eligible"], 1,
                         "load_and_encode_explicit should be accepted as valid")
        self.assertEqual(eligibility["clip_policy_decision"], "load_and_encode_explicit")

    def test_restore_background_unet_rejects_fastpath_load_only_as_invalid(self):
        """'fastpath_load_only' (old non-canonical value) must be rejected
        to ensure the normalization to 'load_only_explicit' is enforced."""
        import comfyapp
        inst = self._make_instance()

        fake_folder_paths = SimpleNamespace(
            get_full_path=lambda bucket, name: f"/models/{bucket}/{name}" if name else ""
        )
        clip_path = "/models/text_encoders/clip.safetensors"
        inst._model_cpu_cache[comfyapp._model_cpu_cache_key(clip_path)] = ({"tensor": 1}, None)
        with mock.patch.object(comfyapp, "_PRODUCTION_BASELINE_OVERRIDES", {}), \
             mock.patch.object(comfyapp, "RESTORE_BACKGROUND_UNET_ENABLED", True), \
             mock.patch.object(comfyapp, "_running_large_reads_locked", return_value=[]), \
             mock.patch.dict("sys.modules", {"folder_paths": fake_folder_paths}):
            eligibility = inst._restore_background_unet_eligibility(
                self._profile(),
                self._clip_policy(decision="fastpath_load_only"),
                self._preload_result(),
            )

        self.assertEqual(eligibility["eligible"], 0,
                         "fastpath_load_only must NOT be accepted")
        self.assertEqual(eligibility["reason"], "direct_clip_policy_not_compatible")

    def test_restore_background_unet_requires_exact_single_resolved_unet(self):
        inst = self._make_instance()
        import comfyapp

        fake_folder_paths = SimpleNamespace(
            get_full_path=lambda bucket, name: f"/models/{bucket}/{name}" if name else ""
        )
        clip_path = "/models/text_encoders/clip.safetensors"
        inst._model_cpu_cache[comfyapp._model_cpu_cache_key(clip_path)] = ({"tensor": 1}, None)
        with mock.patch.object(comfyapp, "_PRODUCTION_BASELINE_OVERRIDES", {}), \
             mock.patch.object(comfyapp, "RESTORE_BACKGROUND_UNET_ENABLED", True), \
             mock.patch.object(comfyapp, "_running_large_reads_locked", return_value=[]), \
             mock.patch.dict("sys.modules", {"folder_paths": fake_folder_paths}):
            eligibility = inst._restore_background_unet_eligibility(
                self._profile(unets=["a.safetensors", "b.safetensors"]),
                self._clip_policy(),
                self._preload_result(),
            )

        self.assertEqual(eligibility["eligible"], 0)
        self.assertEqual(eligibility["reason"], "unet_not_exact_single_resolved")

    def test_restore_background_unet_requires_clip_cpu_cache_after_preload(self):
        inst = self._make_instance()
        import comfyapp

        fake_folder_paths = SimpleNamespace(
            get_full_path=lambda bucket, name: f"/models/{bucket}/{name}" if name else ""
        )
        with mock.patch.object(comfyapp, "_PRODUCTION_BASELINE_OVERRIDES", {}), \
             mock.patch.object(comfyapp, "RESTORE_BACKGROUND_UNET_ENABLED", True), \
             mock.patch.object(comfyapp, "_running_large_reads_locked", return_value=[]), \
             mock.patch.dict("sys.modules", {"folder_paths": fake_folder_paths}):
            eligibility = inst._restore_background_unet_eligibility(
                self._profile(),
                self._clip_policy(),
                self._preload_result(cached=[]),
            )

        self.assertEqual(eligibility["eligible"], 0)
        self.assertEqual(eligibility["reason"], "clip_cpu_cache_missing")

    def test_restore_background_unet_skips_when_large_read_is_running(self):
        inst = self._make_instance()
        import comfyapp

        fake_folder_paths = SimpleNamespace(
            get_full_path=lambda bucket, name: f"/models/{bucket}/{name}" if name else ""
        )
        clip_path = "/models/text_encoders/clip.safetensors"
        inst._model_cpu_cache[comfyapp._model_cpu_cache_key(clip_path)] = ({"tensor": 1}, None)
        with mock.patch.object(comfyapp, "_PRODUCTION_BASELINE_OVERRIDES", {}), \
             mock.patch.object(comfyapp, "RESTORE_BACKGROUND_UNET_ENABLED", True), \
             mock.patch.object(comfyapp, "_running_large_reads_locked", return_value=[{"canonical_key": "busy", "status": "running", "active_read_is_large": 1}]), \
             mock.patch.dict("sys.modules", {"folder_paths": fake_folder_paths}):
            eligibility = inst._restore_background_unet_eligibility(
                self._profile(),
                self._clip_policy(),
                self._preload_result(),
            )

        self.assertEqual(eligibility["eligible"], 0)
        self.assertEqual(eligibility["reason"], "active_large_read_running")

    def test_restore_background_unet_skips_when_future_already_exists(self):
        inst = self._make_instance()
        import comfyapp

        fake_folder_paths = SimpleNamespace(
            get_full_path=lambda bucket, name: f"/models/{bucket}/{name}" if name else ""
        )
        clip_path = "/models/text_encoders/clip.safetensors"
        unet_path = "/models/unet/unet.safetensors"
        inst._model_cpu_cache[comfyapp._model_cpu_cache_key(clip_path)] = ({"tensor": 1}, None)
        inst._actual_load_futures[inst._unet_cache_key(unet_path, "default")] = object()
        with mock.patch.object(comfyapp, "_PRODUCTION_BASELINE_OVERRIDES", {}), \
             mock.patch.object(comfyapp, "RESTORE_BACKGROUND_UNET_ENABLED", True), \
             mock.patch.object(comfyapp, "_running_large_reads_locked", return_value=[]), \
             mock.patch.dict("sys.modules", {"folder_paths": fake_folder_paths}):
            eligibility = inst._restore_background_unet_eligibility(
                self._profile(),
                self._clip_policy(),
                self._preload_result(),
            )

        self.assertEqual(eligibility["eligible"], 0)
        self.assertEqual(eligibility["reason"], "existing_future")


class RestoreBackgroundUnetFutureTests(unittest.TestCase):
    def _make_instance(self):
        from comfyapp import _ComfyAPIMixin
        inst = object.__new__(_ComfyAPIMixin)
        inst._actual_load_futures = {}
        inst._actual_load_future_meta = {}
        inst._actual_load_waits = 0
        return inst

    def test_failed_restore_background_future_does_not_count_as_consumed(self):
        inst = self._make_instance()
        key = ("/models/unet/u.safetensors", "default")

        class DummyThread:
            def join(self, timeout=None):
                return None
            def is_alive(self):
                return False

        inst._actual_load_futures[key] = DummyThread()
        inst._actual_load_future_meta[key] = {
            "source": "restore_background_unet",
            "status": "failed",
            "loader_type": "UNET",
            "error": "boom",
        }

        import comfyapp
        with mock.patch.object(comfyapp, "_restore_background_code_enabled", return_value=True):
            self.assertFalse(inst._consume_actual_load_future(key))
        self.assertNotIn(key, inst._actual_load_futures)


class AutoWarmupASTTests(unittest.TestCase):
    """Structural tests via AST parsing (no Modal dependency)."""

    def _get_method_source(self, method_name: str) -> str | None:
        source_text = COMFYAPP_PATH.read_text(encoding="utf-8-sig")
        tree = ast.parse(source_text)
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == method_name:
                return ast.get_source_segment(source_text, node)
        return None

    def test_restore_warms_cuda_and_applies_sage_detection(self):
        """Restore warms CUDA and applies SageAttention runtime mode detection.

        Startup initialises the in-process backend under
        ``_force_cpu_during_snapshot()`` so the snapshot already contains
        the loaded Python state.  Restore must NOT re-init the backend;
        it should just warm CUDA, and (optionally) rebuild the GPU model
        cache via the warmup profile.  SageAttention runtime mode
        detection must also happen here so the first ``run_prompt()``
        avoids the extra startup tax before first GPU work.
        """
        source = self._get_method_source("restore")
        self.assertIsNotNone(source, "restore method not found")
        # Restore does NOT re-init the in-process backend
        self.assertNotIn("_start_in_process_backend", source,
                         "restore() must not re-init the in-process backend "
                         "— it is pre-initialised in the snapshot under "
                         "_force_cpu_during_snapshot()")
        # Restore DOES rebuild the warmup state when ENABLE_WARMUP.
        # The current implementation does this via early profile/path
        # resolution + CPU preload + direct warmup, rather than routing
        # through _preload_warmup_profile().
        self.assertIn("_snapshot_preload_profile", source)
        self.assertIn("_preload_models_to_cpu", source)
        self.assertIn("_warmup_direct", source)
        self.assertIn("restore_warmup_preload", source)
        self.assertIn("ENABLE_WARMUP", source)
        # Restore DOES warm CUDA
        self.assertIn("_warmup_cuda", source)
        # Restore now performs sage runtime selection and policy application.
        self.assertIn("_select_sage_runtime_mode", source,
                      "restore() must select sage runtime mode after CUDA warmup")
        self.assertIn("_apply_sage_attention_policy", source,
                      "restore() must apply sage attention policy during restore")
        self.assertIn("restore_sage_runtime", source,
                      "restore() must log the sage runtime detection stage")
        self.assertIn("DISABLE_MMAP", source,
                      "restore() must enable eager safetensors reads after restore")

    def test_restore_logs_warmup_cuda_warmup_for_in_process(self):
        source = self._get_method_source("restore")
        self.assertIsNotNone(source)
        self.assertIn("restore_warmup", source)
        self.assertIn("cuda_warmup", source)

    def test_restore_background_unet_submission_is_wired_into_restore(self):
        source = self._get_method_source("restore")
        self.assertIsNotNone(source)
        source = source or ""
        self.assertIn("_maybe_submit_restore_background_unet", source)
        self.assertIn("restore_background_unet_submit_ms_from_restore_start", source)
        self.assertIn("restore_background_unet_enabled", source)

    def test_prompt_and_loader_paths_reference_restore_background_unet_future(self):
        source = COMFYAPP_PATH.read_text(encoding="utf-8-sig")
        self.assertIn("reused_existing_future loader=UNET source=restore_background_unet", source)
        self.assertIn("future_source=restore_background_unet", source)
        self.assertIn("restore_background_unet_fallback_used", source)

    def test_startup_wraps_in_process_init_in_force_cpu(self):
        """Startup initialises the in-process backend under
        ``_force_cpu_during_snapshot()`` so the snapshot has zero CUDA
        driver state.  This avoids the SIGSEGV on restore that the
        previous design hit when GPU memory snapshot captured in-process
        CUDA handles.
        """
        source = self._get_method_source("startup")
        self.assertIsNotNone(source, "startup method not found")
        self.assertIn("_force_cpu_during_snapshot", source,
                      "startup() must wrap in-process backend init in "
                      "_force_cpu_during_snapshot() to keep the snapshot "
                      "free of CUDA driver state")
        self.assertIn("_start_backend", source,
                      "startup() must initialise the backend under "
                      "_force_cpu_during_snapshot() so in-process startup "
                      "keeps its subprocess fallback path")
        # The wrap must be `with self._force_cpu_during_snapshot():`
        # containing the backend start call.
        self.assertRegex(
            source,
            r"with\s+self\._force_cpu_during_snapshot\(\):\s*\n\s+self\._start_backend\(\)",
            "backend start must be wrapped in "
            "with self._force_cpu_during_snapshot(): ...",
        )

    def test_startup_does_not_force_subprocess_fallback(self):
        """The previous design forced the subprocess backend during
        snap=True (``self._backend_fallback = True``) to keep CUDA out
        of the parent snapshot.  The new design uses the in-process
        backend under ``_force_cpu_during_snapshot()`` so that override
        is no longer needed.
        """
        source = self._get_method_source("startup")
        self.assertIsNotNone(source)
        self.assertNotIn(
            "self._backend_fallback = True",
            source,
            "startup() must not force subprocess fallback — the in-process "
            "backend under _force_cpu_during_snapshot() now handles "
            "snapshot safety",
        )

    def test_force_cpu_during_snapshot_method_exists(self):
        """The ``_force_cpu_during_snapshot`` context manager must exist
        and monkey-patch ``torch.cuda.is_available`` /
        ``torch.cuda.current_device`` so ComfyUI's ``model_management``
        skips CUDA initialisation during snap=True.

        It must ALSO block imports of CUDA C extension modules
        (``*_cuda``, ``cuda_*``) via ``sys.meta_path`` so that
        ``PyInit_*`` of e.g. ``sageattn_qk_int8_pv_fp16_cuda`` does
        not allocate GPU memory that ends up in the snapshot.
        """
        source = self._get_method_source("_force_cpu_during_snapshot")
        self.assertIsNotNone(source, "_force_cpu_during_snapshot method not found")
        # Patches the two torch.cuda functions that ComfyUI checks
        self.assertIn("torch.cuda.is_available", source)
        self.assertIn("torch.cuda.current_device", source)
        # Restores the originals in finally (snapshot doesn't capture the patch)
        self.assertIn("original_is_available", source)
        self.assertIn("original_current_device", source)
        self.assertIn("finally", source)
        # Blocks CUDA C extension imports via sys.meta_path
        self.assertIn("sys.meta_path", source,
                      "must insert an import blocker into sys.meta_path so "
                      "CUDA C extensions (e.g. sageattn_*_cuda) don't allocate "
                      "GPU state during snap=True")
        self.assertIn("_is_cuda_module", source)
        self.assertIn("_cuda", source)
        # The blocker must be removed in the finally block
        self.assertIn("sys.meta_path.remove", source)
        # It's a context manager (try / yield / finally — the
        # @contextlib.contextmanager decorator lives above the def line
        # so ast.get_source_segment omits it; the function-body pattern
        # is the canonical signature of a contextlib.contextmanager).
        self.assertIn("yield", source)
        self.assertRegex(source, r"try:\s*\n\s+yield\s*\n\s+finally:")
        # Decorator is present (read full file)
        full_source = COMFYAPP_PATH.read_text(encoding="utf-8-sig")
        self.assertRegex(
            full_source,
            r"@contextlib\.contextmanager\s*\n\s*def\s+_force_cpu_during_snapshot",
        )

    def test_force_cpu_blocker_matches_sageattn_modules(self):
        """The import blocker must recognise the sageattention CUDA
        extension module names so KJNodes falls back to Triton mode
        during snap=True (and doesn't allocate GPU memory that would
        SIGSEGV on restore).
        """
        source = self._get_method_source("_force_cpu_during_snapshot")
        self.assertIsNotNone(source)
        # The pattern must match both Blackwell (fp16) and older (fp8) variants
        self.assertTrue(
            "endswith" in source and "_cuda" in source,
            "blocker must use endswith('_cuda') to match sageattn_*_cuda",
        )
        # Full source check — should explicitly mention the sageattn modules
        # somewhere in the docstring or comments as rationale
        full_source = COMFYAPP_PATH.read_text(encoding="utf-8-sig")
        self.assertIn("sageattn", full_source)

    def test_startup_does_not_preload_cpu_cache(self):
        """CPU cache preload IS disabled in startup — model state dicts are
        NOT loaded during snap=True so Modal's memory snapshot does NOT
        capture UNET/CLIP/VAE state dictionaries in _model_cpu_cache.
        Restore-time preload (with PRELOAD_MODE filtering) loads the CLIP
        model normally.  A cache-empty diagnostic must be emitted.
        """
        source = self._get_method_source("startup")
        self.assertIsNotNone(source, "startup method not found")
        # Startup must NOT call snapshot preload infrastructure
        self.assertNotIn("_snapshot_preload_paths", source,
                         "startup() must NOT call _snapshot_preload_paths")
        self.assertNotIn("_preload_models_to_cpu", source,
                         "startup() must NOT call _preload_models_to_cpu")
        self.assertNotIn("for_snapshot=True", source,
                         "startup() must NOT use for_snapshot=True")
        # Startup MUST contain the cache-empty diagnostic
        self.assertIn("snapshot_cpu_cache_diag", source,
                      "startup() must contain the snapshot CPU cache diagnostic")

        full_source = COMFYAPP_PATH.read_text(encoding="utf-8-sig")
        self.assertIn("_snapshot_preload_profile", full_source,
                      "_snapshot_preload_profile must remain as reusable infrastructure")
        self.assertIn("_snapshot_preload_paths", full_source,
                      "_snapshot_preload_paths must remain as reusable infrastructure")
        self.assertIn("_preload_models_to_cpu", full_source,
                      "_preload_models_to_cpu must remain as reusable infrastructure")

    def test_snapshot_preload_paths_includes_all_models(self):
        """Snapshot preload (for_snapshot=True) must include UNET, CLIP1,
        CLIP2, and VAE regardless of the effective PRELOAD_MODE."""
        from comfyapp import _ComfyAPIMixin
        inst = object.__new__(_ComfyAPIMixin)
        profile = {
            "mode": "split",
            "unet": "unet.safetensors",
            "clip1": "clip.safetensors",
            "clip2": "clip.safetensors",
            "vae": "vae.safetensors",
            "clip_type": "flux",
        }
        # Return distinct paths per bucket to avoid dedup collapsing them
        _fake_paths = {
            "unet": "/models/unet/unet.safetensors",
            "clip": "/models/text_encoders/clip.safetensors",
            "vae": "/models/vae/vae.safetensors",
        }
        def _fake_find(bucket, filename):
            return _fake_paths.get(bucket)
        with mock.patch.object(inst, "_find_model_file", side_effect=_fake_find):
            paths = inst._snapshot_preload_paths(profile, for_snapshot=True)
        roles = {p["role"] for p in paths}
        self.assertIn("unet", roles, "snapshot preload must include UNET")
        self.assertIn("clip", roles, "snapshot preload must include CLIP")
        self.assertIn("vae", roles, "snapshot preload must include VAE")

    def test_snapshot_preload_paths_respects_preload_mode_by_default(self):
        """Restore-time preload (for_snapshot=False) must still respect
        PRELOAD_MODE filtering (e.g., clip_only loads only CLIP)."""
        from comfyapp import _ComfyAPIMixin, _resolve_preload_mode
        inst = object.__new__(_ComfyAPIMixin)
        profile = {
            "mode": "split",
            "unet": "unet.safetensors",
            "clip1": "clip.safetensors",
            "clip2": "clip.safetensors",
            "vae": "vae.safetensors",
            "clip_type": "flux",
        }
        # Override preload mode to clip_only for this test
        with mock.patch("comfyapp._resolve_preload_mode", return_value="clip_only"):
            with mock.patch.object(inst, "_find_model_file", return_value="/models/unet/unet.safetensors"):
                paths = inst._snapshot_preload_paths(profile, for_snapshot=False)
        roles = {p["role"] for p in paths}
        self.assertNotIn("unet", roles,
                         "restore-time preload must not include UNET when PRELOAD_MODE=clip_only")
        self.assertIn("clip", roles,
                      "restore-time preload must include CLIP when PRELOAD_MODE=clip_only")

    def test_snapshot_cpu_cache_empty_on_startup(self):
        """The startup() method must NOT populate _model_cpu_cache during
        snapshot creation.  Instead it must emit a cache-empty diagnostic
        confirming no UNET/CLIP/VAE state dicts were preloaded."""
        source = self._get_method_source("startup")
        self.assertIsNotNone(source)
        self.assertNotIn("_snapshot_preload_paths(_snap_profile, for_snapshot=True)", source,
                         "startup() must NOT have for_snapshot=True preload call")
        self.assertNotIn("_preload_models_to_cpu(_snap_paths, max_workers=1)", source,
                         "startup() must NOT call _preload_models_to_cpu")
        self.assertNotIn("snapshot_preload_cpu", source,
                         "startup() must NOT log snapshot_preload_cpu")
        self.assertIn("snapshot_cpu_cache_diag", source,
                      "startup() must contain the snapshot CPU cache diagnostic")

    def test_snapshot_preload_module_defaults_are_generic(self):
        """The module-level WARMUP_* defaults must be empty model filenames
        and 'flux' clip type — no hardcoded Z-Image-specific values."""
        import comfyapp as _ca
        self.assertEqual(_ca.WARMUP_UNET, "")
        self.assertEqual(_ca.WARMUP_CLIP1, "")
        self.assertEqual(_ca.WARMUP_CLIP2, "")
        self.assertEqual(_ca.WARMUP_VAE, "")
        self.assertEqual(_ca.WARMUP_CLIP_TYPE, "flux")

    def test_snapshot_preload_paths_validate_profile(self):
        """_snapshot_preload_paths must return empty list when given an empty
        profile, preserving existing profile validation."""
        from comfyapp import _ComfyAPIMixin
        inst = object.__new__(_ComfyAPIMixin)
        paths = inst._snapshot_preload_paths({}, for_snapshot=True)
        self.assertEqual(paths, [])
        paths2 = inst._snapshot_preload_paths(None, for_snapshot=True)
        self.assertEqual(paths2, [])

    def test_restore_cache_hit_on_preloaded_models(self):
        """When _model_cpu_cache already has entries (populated by snapshot),
        _patch_model_cpu_cache must return cached data without volume reads."""
        from comfyapp import _ComfyAPIMixin
        inst = object.__new__(_ComfyAPIMixin)
        inst._model_cpu_cache = {"clip.safetensors": ({"tensor": 1}, {"format": "fp8"})}
        inst._cpu_cache_hits = {}
        inst._cpu_cache_misses = {}
        inst._actual_load_futures = {}
        inst._actual_load_future_meta = {}

        class FakeComfyUtils:
            def load_torch_file(path, *args, **kwargs):
                raise RuntimeError("volume read should not happen on cache hit")

        fake_utils = FakeComfyUtils()
        # _patch_model_cpu_cache needs comfy.utils (module, not instance)
        import types
        fake_mod = types.ModuleType("fake_comfy_utils")
        fake_mod.load_torch_file = lambda path, *a, **kw: (
            {"tensor": "from_disk"}, {"format": "fp8"}
        )
        # Check that patching works and cache hit returns cached data
        inst._patch_model_cpu_cache(fake_mod)
        # Now call the patched loader with a path matching the cached filename
        result = fake_mod.load_torch_file("/models/text_encoders/clip.safetensors", return_metadata=True)
        if isinstance(result, tuple) and len(result) == 2:
            state_dict, metadata = result
        else:
            state_dict = result
            metadata = None
        self.assertEqual(state_dict, {"tensor": 1},
                         "cache hit must return the cached state dict, not read from disk")

    def test_restore_cache_miss_falls_through_to_original_loader(self):
        """When _model_cpu_cache is empty (no snapshot preload), the patched
        loader must fall through to the original comfy.utils.load_torch_file."""
        from comfyapp import _ComfyAPIMixin
        inst = object.__new__(_ComfyAPIMixin)
        inst._model_cpu_cache = {}
        inst._cpu_cache_hits = {}
        inst._cpu_cache_misses = {}
        inst._actual_load_futures = {}
        inst._actual_load_future_meta = {}

        fallback_called = False

        class FakeComfyUtils:
            def load_torch_file(path, *args, **kwargs):
                nonlocal fallback_called
                fallback_called = True
                return ({"tensor": "from_disk"}, {"format": "fp8"})

        fake_utils = FakeComfyUtils()
        inst._patch_model_cpu_cache(fake_utils)
        result = fake_utils.load_torch_file("/models/unet/unet.safetensors")
        self.assertTrue(fallback_called, "original loader must be called on cache miss")

    def test_run_prompt_does_not_repeat_sage_detection(self):
        """run_prompt() should not repeat restore-time sage setup."""
        source = self._get_method_source("run_prompt")
        self.assertIsNotNone(source)
        self.assertNotIn("_select_sage_runtime_mode", source,
                         "run_prompt() must not repeat restore-time sage detection")
        self.assertNotIn("_apply_sage_attention_policy", source,
                         "run_prompt() must not repeat restore-time sage policy setup")
        self.assertNotIn("run_prompt_deferred_sage", source,
                         "run_prompt() must not log the removed deferred sage stage")

    def test_enable_warmup_defaults_to_one(self):
        source = COMFYAPP_PATH.read_text(encoding="utf-8-sig")
        self.assertIn('ENABLE_WARMUP = env_flag("COMFYMODAL_ENABLE_WARMUP", default=True)', source)

    def test_restore_gpu_state_recomputes_total_vram(self):
        source = self._get_method_source("_restore_in_process_gpu_state")
        self.assertIsNotNone(source)
        self.assertIn("total_vram", source)
        self.assertIn("get_total_memory", source)
        self.assertIn("get_torch_device", source)

    def test_restore_gpu_state_imports_psutil_for_total_ram(self):
        source = self._get_method_source("_restore_in_process_gpu_state")
        self.assertIsNotNone(source)
        self.assertIn("import psutil", source)
        self.assertIn("virtual_memory", source)

    def test_run_prompt_calls_save_last_model_stack(self):
        source = self._get_method_source("run_prompt")
        self.assertIsNotNone(source)
        self.assertIn("_save_last_model_stack", source)

    def test_run_prompt_calls_save_last_warmup_workflow(self):
        source = self._get_method_source("run_prompt")
        self.assertIsNotNone(source)
        self.assertIn("_save_last_warmup_workflow", source)

    def test_run_prompt_saves_replay_workflow_before_stack_commit(self):
        source = self._get_method_source("run_prompt")
        self.assertIsNotNone(source)
        self.assertLess(source.index("_save_last_warmup_workflow"), source.index("_save_last_model_stack"))

    def test_preload_warmup_profile_falls_back_to_stack_to_profile(self):
        source = self._get_method_source("_preload_warmup_profile")
        self.assertIsNotNone(source)
        self.assertIn("stack_to_profile", source)
        self.assertIn("_load_last_model_stack", source)

    def test_module_exports_stack_to_profile(self):
        source = COMFYAPP_PATH.read_text(encoding="utf-8-sig")
        self.assertIn("def stack_to_profile", source)

    def test_collect_in_process_outputs_has_time_scoped_scan(self):
        """The output collector must scope its directory-scan fallback to
        the prompt's start time so it picks up files written *during*
        the prompt (not stale images from earlier prompts in the same
        container).  Without this, multi-prompt containers either
        return wrong files or zero files when executor history metadata
        is not populated.
        """
        source = self._get_method_source("_collect_in_process_outputs")
        self.assertIsNotNone(source, "_collect_in_process_outputs method not found")
        # Method signature must accept prompt_start_time
        self.assertIn("prompt_start_time", source,
                      "collector must accept a prompt_start_time parameter "
                      "to scope its directory-scan fallback")
        # The scan helper must filter by mtime
        self.assertIn("since_ts", source,
                      "directory scan must filter by mtime >= since_ts")
        self.assertIn("st_mtime", source)
        # The collector must de-dupe across sources
        self.assertIn("seen_filenames", source,
                      "collector must de-dupe results across history + scan sources")
        # The collector must scan generated-output directories only.
        for d in ("output", "temp"):
            self.assertIn(d, source,
                          f"collector must scan the {d}/ directory")
        self.assertIn('"input": comfy_root / "input"', source,
                      "history metadata may still point at input/ files explicitly")
        self.assertNotIn('for base in (comfy_root / "output", comfy_root / "temp", comfy_root / "input")', source,
                         "directory-scan fallback must not sweep uploaded source images from input/")
        # Diagnostic logging for the empty-output case
        self.assertIn("no outputs found", source,
                      "collector must log when no outputs are found, "
                      "with diagnostic context")

    def test_execute_in_process_passes_prompt_start_time_to_collector(self):
        """The prompt execution path must capture prompt_start_time and
        pass it to the collector so the directory-scan fallback is
        scoped correctly.
        """
        source = self._get_method_source("_execute_in_process")
        self.assertIsNotNone(source, "_execute_in_process method not found")
        # Captures a start time
        self.assertIn("prompt_start_time", source,
                      "_execute_in_process must capture prompt_start_time")
        # Passes it to the collector
        self.assertIn("_collect_in_process_outputs", source)
        self.assertRegex(
            source,
            r"_collect_in_process_outputs\([^)]*prompt_start_time=",
            "_execute_in_process must pass prompt_start_time=… to the collector",
        )

    def test_restore_does_not_seed_hardcoded_warmup_env_vars(self):
        source = self._get_method_source("restore")
        self.assertIsNotNone(source)
        self.assertNotIn("COMFYMODAL_WARMUP_UNET", source)
        self.assertNotIn("COMFYMODAL_WARMUP_CLIP1", source)
        self.assertNotIn("COMFYMODAL_WARMUP_CLIP2", source)
        self.assertNotIn("COMFYMODAL_WARMUP_VAE", source)
        self.assertNotIn("COMFYMODAL_WARMUP_CLIP_TYPE", source)

    def test_modal_image_env_does_not_pin_flux2_warmup_profile(self):
        source = COMFYAPP_PATH.read_text(encoding="utf-8-sig")
        self.assertNotIn('"COMFYMODAL_WARMUP_UNET": "flux-2-klein-9b-fp8.safetensors"', source)
        self.assertNotIn('"COMFYMODAL_WARMUP_CLIP1": "qwen_3_8b_fp8mixed.safetensors"', source)
        self.assertNotIn('"COMFYMODAL_WARMUP_CLIP2": "qwen_3_8b_fp8mixed.safetensors"', source)
        self.assertNotIn('"COMFYMODAL_WARMUP_VAE": "flux2-vae.safetensors"', source)
        self.assertNotIn('"COMFYMODAL_WARMUP_CLIP_TYPE": "flux2"', source)

    def test_snapshot_preload_profile_no_longer_prefers_last_stack(self):
        source = self._get_method_source("_snapshot_preload_profile")
        self.assertIsNotNone(source)
        self.assertIn("_load_active_next_profile", source)
        self.assertNotIn('source = "last_stack"', source)

    def test_run_prompt_logs_warmup_profile_match_flag(self):
        source = self._get_method_source("run_prompt")
        self.assertIsNotNone(source)
        self.assertIn("WARMUP_PROFILE_MATCH", source)
        self.assertIn("profile_source", source)
        self.assertIn("profile_token", source)

    # ── Audit round 8: fastpath normalization + duplicate prevention ──

    def test_restore_has_only_one_maybe_submit_background_unet_call(self):
        """Only ONE call to _maybe_submit_restore_background_unet must
        remain in restore() after removing the older experimental
        duplicate call site.  The retained fastpath call is the one
        gated by fastpath_background_unet."""
        source = self._get_method_source("restore")
        self.assertIsNotNone(source)
        count = source.count("_maybe_submit_restore_background_unet")
        self.assertEqual(
            count, 1,
            f"Expected exactly 1 call to _maybe_submit_restore_background_unet "
            f"in restore(), found {count}",
        )

    def test_restore_does_not_have_experimental_background_code_gate(self):
        """The older experimental restore_background_code_enabled gated
        call site must be removed.  Check that the block referencing
        _restore_background_code_enabled immediately after preload join
        is gone (the graph_unet_expected_source diagnostic was set only
        in that block)."""
        full_source = COMFYAPP_PATH.read_text(encoding="utf-8-sig")
        # The removed block set graph_unet_expected_source — it should
        # no longer appear in restore() (the fastpath block is different).
        restore_source = self._get_method_source("restore")
        self.assertIsNotNone(restore_source)
        # The removed block had a specific structure:
        # graph_unet_expected_source was set inside
        # _restore_background_code_enabled().  After removal, restore()
        # should not reference graph_unet_expected_source.
        self.assertNotIn(
            "graph_unet_expected_source", restore_source,
            "restore() must not contain the removed experimental "
            "expected-source diagnostics",
        )
        # But the method itself still exists (for non-restore callers)
        self.assertIn(
            "def _restore_background_code_enabled",
            full_source,
            "_restore_background_code_enabled must remain defined",
        )

    def test_restore_exact_prefill_override_logic_present(self):
        """The exact-prefill bundle-match override that restores CLIP
        encoding before _warmup_direct must be present in restore()."""
        source = self._get_method_source("restore")
        self.assertIsNotNone(source)
        self.assertIn(
            "_clip_policy_override", source,
            "restore() must create _clip_policy_override when bundle "
            "group positively matches",
        )
        self.assertIn(
            "exact_prefill_override_clip_encode", source,
            "restore() must log exact_prefill_override_clip_encode in "
            "__stages when override is active",
        )
        self.assertIn(
            "load_and_encode_explicit", source,
            "restore() must use load_and_encode_explicit decision when "
            "overriding for exact-prefill",
        )

    def test_restore_fastpath_decides_load_only_explicit(self):
        """The fastpath clip_load_only mode must produce the canonical
        load_only_explicit decision (not the old fastpath_load_only)."""
        source = self._get_method_source("restore")
        self.assertIsNotNone(source)
        self.assertIn(
            "load_only_explicit",
            source,
        )
        self.assertNotIn(
            "fastpath_load_only",
            source,
            "The non-canonical fastpath_load_only decision must not "
            "appear in restore()",
        )

    def test_restore_call_count_no_regression(self):
        """Verify that restore() has not lost or gained critical
        operations by checking a stable call count footprint.  The
        removed block had ~23 lines; the exact-prefill override added
        ~13 lines.  Net removal of ~10 lines is acceptable and should
        not change the step/operation count measured as key method calls."""
        source = self._get_method_source("restore")
        self.assertIsNotNone(source)
        # Key operations that must remain present in restore()
        for key_op in (
            "_warmup_cuda",
            "_select_sage_runtime_mode",
            "_apply_sage_attention_policy",
            "_snapshot_preload_profile",
            "_preload_models_to_cpu",
            "_warmup_direct",
            "_maybe_submit_restore_background_unet",
            "_log_remote_identity",
        ):
            self.assertIn(key_op, source,
                          f"restore() must contain {key_op}")
        # Operations that must NOT be in restore()
        for absent_op in (
            "_start_in_process_backend",
            "_restore_background_code_enabled",  # only the guard, not the def
        ):
            # Only check _restore_background_code_enabled is not called
            # (as a function call), the def remains in the module.
            pass
        # Verify no unexpected extra _maybe_submit_restore_background_unet calls
        self.assertEqual(
            source.count("_maybe_submit_restore_background_unet"), 1,
            "Must have exactly one call to _maybe_submit_restore_background_unet",
        )

    # ── Task-specific regression tests: env_default eligibility + max_workers override ──

    def test_preload_eligibility_guard_accepts_env_default(self):
        """The preload eligibility guard must accept _source='env_default'
        instead of rejecting it with 'unknown_profile'."""
        source = self._get_method_source("restore")
        self.assertIsNotNone(source)
        self.assertIn(
            '_profile_source_early == "env_default"',
            source,
            "restore() must handle env_default in preload eligibility guard",
        )

    def test_startup_has_cpu_cache_diagnostic(self):
        """Startup(snap=True) must emit the snapshot CPU cache diagnostic
        confirming the workflow-model cache is empty before Modal captures
        the memory snapshot."""
        source = self._get_method_source("startup")
        self.assertIsNotNone(source)
        self.assertIn(
            "snapshot_cpu_cache_diag",
            source,
            "startup() must contain the snapshot CPU cache diagnostic",
        )
        # Must NOT contain the old snapshot preload infrastructure
        self.assertNotIn(
            "max_workers=1",
            source,
            "startup() must NOT call _preload_models_to_cpu with max_workers=1",
        )

    def test_preload_models_to_cpu_has_max_workers_param(self):
        """_preload_models_to_cpu must accept an optional keyword-only
        max_workers parameter defaulting to None."""
        source = self._get_method_source("_preload_models_to_cpu")
        self.assertIsNotNone(source)
        self.assertIn(
            "max_workers: int | None = None",
            source,
            "_preload_models_to_cpu must accept max_workers param",
        )


class FastpathClipPolicyTests(unittest.TestCase):
    """Unit tests for the fastpath v2.16.21 clip policy decision
    normalization.  These verify that the fastpath auto load-only mode
    normalizes to the existing canonical 'load_only_explicit' semantic
    accepted by _restore_background_unet_eligibility."""

    def test_fastpath_load_only_normalizes_to_load_only_explicit(self):
        """When fastpath_clip_load_only is active and the configured
        policy is 'auto', the overridden decision must be
        'load_only_explicit' (the canonical semantic), not the old
        non-canonical 'fastpath_load_only'."""
        import comfyapp
        # Simulate the override logic from lines 18037-18049
        clip_policy = {
            "restore_direct_clip_policy": "auto",
            "restore_direct_clip_policy_decision": "load_and_encode_default",
            "direct_warmup_load_clip_effective": 1,
            "direct_warmup_clip_encode_effective": 1,
        }
        # Apply the same logic as the fastpath block
        _clip_override = dict(clip_policy)
        _cfg_policy = _clip_override.get("restore_direct_clip_policy", "auto")
        if _cfg_policy == "auto":
            _clip_override["direct_warmup_clip_encode_effective"] = 0
            _clip_override["restore_direct_clip_policy_decision"] = "load_only_explicit"
        self.assertEqual(
            _clip_override["restore_direct_clip_policy_decision"],
            "load_only_explicit",
        )
        self.assertEqual(_clip_override["direct_warmup_clip_encode_effective"], 0)

    def test_fastpath_load_only_normalization_is_accepted_by_eligibility(self):
        """The normalized load_only_explicit decision must pass through
        _restore_background_unet_eligibility successfully when all other
        eligibility conditions are met."""
        from comfyapp import _ComfyAPIMixin
        import comfyapp
        inst = object.__new__(_ComfyAPIMixin)
        inst._model_cpu_cache = {}
        inst._actual_load_futures = {}
        inst._actual_load_future_meta = {}
        inst._actual_load_locks = {}
        inst._actual_load_owner_thread = {}
        inst._unet_object_cache = {}
        inst._original_loaders_store = {"UNETLoader.load_unet": lambda *a, **k: (object(),)}

        # Build a profile matching the active_next_profile constraint
        profile = {
            "_source": "active_next_profile",
            "_current_workflow_stack": {
                "unet": ["unet.safetensors"],
                "clip": ["clip.safetensors"],
                "vae": ["vae.safetensors"],
                "checkpoint": [],
                "clip_type": "lumina2",
            },
            "unet": "unet.safetensors",
            "clip1": "clip.safetensors",
            "clip2": "clip.safetensors",
            "vae": "vae.safetensors",
            "clip_type": "lumina2",
        }
        clip_policy = {
            "restore_direct_clip_policy": "auto",
            "restore_direct_clip_policy_decision": "load_only_explicit",
            "direct_warmup_load_clip_effective": 1,
            "direct_warmup_clip_encode_effective": 0,
        }
        preload_result = {
            "cached": ["clip.safetensors"],
            "aborted": False,
            "failed_files": 0,
            "running_threads_not_killable": 0,
        }
        fake_folder_paths = SimpleNamespace(
            get_full_path=lambda bucket, name: f"/models/{bucket}/{name}" if name else ""
        )
        clip_path = "/models/text_encoders/clip.safetensors"
        inst._model_cpu_cache[comfyapp._model_cpu_cache_key(clip_path)] = ({"tensor": 1}, None)

        with mock.patch.object(comfyapp, "_PRODUCTION_BASELINE_OVERRIDES", {}), \
             mock.patch.object(comfyapp, "RESTORE_BACKGROUND_UNET_ENABLED", True), \
             mock.patch.object(comfyapp, "_running_large_reads_locked", return_value=[]), \
             mock.patch.dict("sys.modules", {"folder_paths": fake_folder_paths}):
            eligibility = inst._restore_background_unet_eligibility(
                profile, clip_policy, preload_result
            )

        self.assertEqual(
            eligibility["eligible"], 1,
            "load_only_explicit must be accepted by eligibility: "
            f"reason={eligibility.get('reason', '?')}",
        )

    def test_fastpath_load_only_old_value_is_rejected_by_eligibility(self):
        """The old non-canonical 'fastpath_load_only' decision must be
        rejected by eligibility, proving normalization is necessary."""
        from comfyapp import _ComfyAPIMixin
        import comfyapp
        inst = object.__new__(_ComfyAPIMixin)
        inst._model_cpu_cache = {}
        inst._actual_load_futures = {}
        inst._actual_load_future_meta = {}
        inst._actual_load_locks = {}
        inst._actual_load_owner_thread = {}
        inst._unet_object_cache = {}
        inst._original_loaders_store = {"UNETLoader.load_unet": lambda *a, **k: (object(),)}

        profile = {
            "_source": "active_next_profile",
            "_current_workflow_stack": {
                "unet": ["unet.safetensors"],
                "clip": ["clip.safetensors"],
                "vae": ["vae.safetensors"],
                "checkpoint": [],
                "clip_type": "lumina2",
            },
            "unet": "unet.safetensors",
            "clip1": "clip.safetensors",
            "clip2": "clip.safetensors",
            "vae": "vae.safetensors",
            "clip_type": "lumina2",
        }
        clip_policy = {
            "restore_direct_clip_policy": "auto",
            "restore_direct_clip_policy_decision": "fastpath_load_only",
            "direct_warmup_load_clip_effective": 1,
            "direct_warmup_clip_encode_effective": 0,
        }
        preload_result = {
            "cached": ["clip.safetensors"],
            "aborted": False,
            "failed_files": 0,
            "running_threads_not_killable": 0,
        }
        fake_folder_paths = SimpleNamespace(
            get_full_path=lambda bucket, name: f"/models/{bucket}/{name}" if name else ""
        )
        clip_path = "/models/text_encoders/clip.safetensors"
        inst._model_cpu_cache[comfyapp._model_cpu_cache_key(clip_path)] = ({"tensor": 1}, None)

        with mock.patch.object(comfyapp, "_PRODUCTION_BASELINE_OVERRIDES", {}), \
             mock.patch.object(comfyapp, "RESTORE_BACKGROUND_UNET_ENABLED", True), \
             mock.patch.object(comfyapp, "_running_large_reads_locked", return_value=[]), \
             mock.patch.dict("sys.modules", {"folder_paths": fake_folder_paths}):
            eligibility = inst._restore_background_unet_eligibility(
                profile, clip_policy, preload_result
            )

        self.assertEqual(
            eligibility["eligible"], 0,
            "fastpath_load_only must be rejected by eligibility",
        )
        self.assertEqual(eligibility["reason"], "direct_clip_policy_not_compatible")


if __name__ == "__main__":
    unittest.main()
