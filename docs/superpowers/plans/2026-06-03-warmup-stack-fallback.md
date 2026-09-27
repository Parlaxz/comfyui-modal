# Warmup Stack Fallback Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove Flux2-specific warmup profile defaults so restore falls back to the detected last-workflow model stack instead of silently pinning the repo to one hardcoded model set.

**Architecture:** Keep the existing warmup pipeline intact. The only behavior change is to stop injecting default `COMFYMODAL_WARMUP_*` values in the Modal image env map and in `restore()`, allowing `_snapshot_preload_profile()` to continue preferring `last_model_stack` and only use explicit env vars when the user deliberately sets them.

**Tech Stack:** Python, unittest/pytest, Modal app configuration in `comfyapp.py`

---

### Task 1: Add regression tests for "no hardcoded Flux2 fallback"

**Files:**
- Modify: `tests/test_comfyapp_auto_warmup.py`
- Verify against: `comfyapp.py:835-849`
- Verify against: `comfyapp.py:4116-4128`

- [ ] **Step 1: Write the failing tests**

Add these test methods to `tests/test_comfyapp_auto_warmup.py`:

```python
class SnapshotPreloadProfileTests(unittest.TestCase):
    def _make_instance(self):
        from comfyapp import _ComfyAPIMixin
        return object.__new__(_ComfyAPIMixin)

    def test_snapshot_preload_profile_prefers_last_stack_over_env_profile(self):
        inst = self._make_instance()
        inst._load_last_model_stack = lambda: {
            "checkpoint": [],
            "unet": ["actual-unet.safetensors"],
            "clip": ["clip_l.safetensors", "t5xxl_fp16.safetensors"],
            "vae": ["actual-vae.safetensors"],
        }
        with mock.patch.dict(os.environ, {
            "COMFYMODAL_WARMUP_UNET": "env-unet.safetensors",
            "COMFYMODAL_WARMUP_CLIP1": "env-clip-1.safetensors",
            "COMFYMODAL_WARMUP_CLIP2": "env-clip-2.safetensors",
            "COMFYMODAL_WARMUP_VAE": "env-vae.safetensors",
            "COMFYMODAL_WARMUP_CLIP_TYPE": "flux2",
        }, clear=False):
            profile = inst._snapshot_preload_profile()

        self.assertEqual(profile["_source"], "last_stack")
        self.assertEqual(profile["unet"], "actual-unet.safetensors")
        self.assertEqual(profile["clip1"], "clip_l.safetensors")
        self.assertEqual(profile["clip2"], "t5xxl_fp16.safetensors")
        self.assertEqual(profile["vae"], "actual-vae.safetensors")

    def test_snapshot_preload_profile_returns_empty_without_stack_or_env_profile(self):
        inst = self._make_instance()
        inst._load_last_model_stack = lambda: {}
        with mock.patch.dict(os.environ, {
            "COMFYMODAL_WARMUP_CHECKPOINT": "",
            "COMFYMODAL_WARMUP_UNET": "",
            "COMFYMODAL_WARMUP_CLIP1": "",
            "COMFYMODAL_WARMUP_CLIP2": "",
            "COMFYMODAL_WARMUP_VAE": "",
            "COMFYMODAL_WARMUP_CLIP_TYPE": "",
        }, clear=False):
            profile = inst._snapshot_preload_profile()

        self.assertIsNone(profile)


class AutoWarmupASTTests(unittest.TestCase):
    def test_restore_does_not_seed_hardcoded_warmup_env_vars(self):
        source = self._get_method_source("restore")
        self.assertIsNotNone(source)
        self.assertNotIn("COMFYMODAL_WARMUP_UNET", source)
        self.assertNotIn("COMFYMODAL_WARMUP_CLIP1", source)
        self.assertNotIn("COMFYMODAL_WARMUP_CLIP2", source)
        self.assertNotIn("COMFYMODAL_WARMUP_VAE", source)
        self.assertNotIn("COMFYMODAL_WARMUP_CLIP_TYPE", source)

    def test_modal_image_env_does_not_pin_flux2_warmup_profile(self):
        source = COMFYAPP_PATH.read_text(encoding="utf-8")
        self.assertNotIn('"COMFYMODAL_WARMUP_UNET": "flux-2-klein-9b-fp8.safetensors"', source)
        self.assertNotIn('"COMFYMODAL_WARMUP_CLIP1": "qwen_3_8b_fp8mixed.safetensors"', source)
        self.assertNotIn('"COMFYMODAL_WARMUP_CLIP2": "qwen_3_8b_fp8mixed.safetensors"', source)
        self.assertNotIn('"COMFYMODAL_WARMUP_VAE": "flux2-vae.safetensors"', source)
        self.assertNotIn('"COMFYMODAL_WARMUP_CLIP_TYPE": "flux2"', source)
```

Place `SnapshotPreloadProfileTests` next to the other small unit-style test classes, before `AutoWarmupASTTests`.

- [ ] **Step 2: Run the tests to verify they fail for the right reason**

Run:

```bash
python -m pytest tests/test_comfyapp_auto_warmup.py -q -k "hardcoded_warmup or snapshot_preload_profile or modal_image_env"
```

Expected:
- `test_restore_does_not_seed_hardcoded_warmup_env_vars` fails because `restore()` still contains the `COMFYMODAL_WARMUP_*` injection block.
- `test_modal_image_env_does_not_pin_flux2_warmup_profile` fails because the Modal image env map still contains Flux2 defaults.
- `test_snapshot_preload_profile_prefers_last_stack_over_env_profile` should pass and documents the intended fallback precedence.
- `test_snapshot_preload_profile_returns_empty_without_stack_or_env_profile` should pass and documents the clean no-profile/no-stack behavior.

- [ ] **Step 3: Commit the red test state only if your workflow explicitly wants red commits**

```bash
git add tests/test_comfyapp_auto_warmup.py
git commit -m "test: guard against hardcoded warmup defaults"
```

If your workflow does not allow red commits, skip this commit and continue directly to Task 2.

### Task 2: Remove the hardcoded Flux2 defaults from runtime setup

**Files:**
- Modify: `comfyapp.py:835-849`
- Modify: `comfyapp.py:4116-4128`
- Test: `tests/test_comfyapp_auto_warmup.py`

- [ ] **Step 1: Remove the Flux2 entries from the Modal image env map**

Change the `.env({...})` block in `comfyapp.py` to this shape:

```python
    .env(
        {
            "TORCHINDUCTOR_CACHE_DIR": "/root/models/.inductor-cache",
            "TORCHINDUCTOR_FX_GRAPH_CACHE": "1",
            "TRITON_CACHE_DIR": "/tmp/triton_cache",
            "TORCHINDUCTOR_EMULATE_PRECISION_CASTS": "1",
            "TORCHINDUCTOR_COMPILE_THREADS": "1",
            "COMFYMODAL_ENABLE_TORCH_COMPILE": "0",
            "COMFYMODAL_ENABLE_GPU_SNAPSHOT": "0",
            "COMFYMODAL_WARMUP_TEXT": "warmup",
        }
    )
```

Do not add any replacement `COMFYMODAL_WARMUP_*` defaults here.

- [ ] **Step 2: Remove the restore-time env injection block**

Delete this block from `restore()` in `comfyapp.py`:

```python
        # Ensure warmup profile env vars are set for testing
        if not os.environ.get("COMFYMODAL_WARMUP_UNET"):
            os.environ["COMFYMODAL_WARMUP_UNET"] = "flux-2-klein-9b-fp8.safetensors"
        if not os.environ.get("COMFYMODAL_WARMUP_CLIP1"):
            os.environ["COMFYMODAL_WARMUP_CLIP1"] = "qwen_3_8b_fp8mixed.safetensors"
        if not os.environ.get("COMFYMODAL_WARMUP_CLIP2"):
            os.environ["COMFYMODAL_WARMUP_CLIP2"] = "qwen_3_8b_fp8mixed.safetensors"
        if not os.environ.get("COMFYMODAL_WARMUP_VAE"):
            os.environ["COMFYMODAL_WARMUP_VAE"] = "flux2-vae.safetensors"
        if not os.environ.get("COMFYMODAL_WARMUP_CLIP_TYPE"):
            os.environ["COMFYMODAL_WARMUP_CLIP_TYPE"] = "flux2"
```

Leave the existing `COMFYMODAL_PRELOAD_MODE` block and the rest of `restore()` unchanged.

- [ ] **Step 3: Run the targeted tests again to verify green**

Run:

```bash
python -m pytest tests/test_comfyapp_auto_warmup.py -q -k "hardcoded_warmup or snapshot_preload_profile or modal_image_env"
```

Expected:
- All selected tests pass.
- The fallback precedence test still reports `_source == "last_stack"`.
- The empty-stack test still returns `None`.

- [ ] **Step 4: Commit the implementation**

```bash
git add comfyapp.py tests/test_comfyapp_auto_warmup.py
git commit -m "fix: remove hardcoded warmup profile defaults"
```

### Task 3: Run the related warmup regression suite

**Files:**
- Verify: `tests/test_comfyapp_auto_warmup.py`
- Verify: `tests/test_runtime_config.py`
- Verify only: `runtime_config.py`

- [ ] **Step 1: Run the warmup and runtime-config test files**

Run:

```bash
python -m pytest tests/test_comfyapp_auto_warmup.py tests/test_runtime_config.py -q
```

Expected:
- Both test files pass.
- No snapshot-key tests change, because `runtime_config.py` still accepts explicit warmup-profile inputs exactly as before.

- [ ] **Step 2: Inspect the diff before final handoff**

Run:

```bash
git diff -- comfyapp.py tests/test_comfyapp_auto_warmup.py
```

Expected:
- Diff only removes hardcoded Flux2 defaults and adds regression coverage.
- No unrelated runtime-config changes appear.

- [ ] **Step 3: Commit the verification checkpoint if your workflow wants a final green commit marker**

```bash
git add comfyapp.py tests/test_comfyapp_auto_warmup.py tests/test_runtime_config.py
git commit -m "test: verify warmup stack fallback regression coverage"
```

Skip this commit if Task 2 already produced the single final green commit your workflow expects.
