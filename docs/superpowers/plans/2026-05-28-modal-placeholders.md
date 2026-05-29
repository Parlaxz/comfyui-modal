# Modal Placeholders Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restore exact-filename local placeholder creation for Modal-hosted models so local ComfyUI dropdowns can reference remote-only models without downloading them locally.

**Architecture:** Add a pure helper module for folder validation and local placeholder creation, route all backend placeholder flows through it, annotate listed remote models with local-file status, and restore explicit placeholder actions in the sidebar while preserving the existing checkpoint-family folder mapping.

**Tech Stack:** Python, aiohttp routes, vanilla JavaScript sidebar UI, built-in unittest

---

### Task 1: Add failing helper tests

**Files:**
- Create: `tests/test_local_placeholders.py`

- [ ] **Step 1: Write the failing test file**

```python
import importlib.util
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = REPO_ROOT / "local_placeholders.py"


def load_module():
    if not MODULE_PATH.exists():
        raise AssertionError("local_placeholders.py missing")
    spec = importlib.util.spec_from_file_location("local_placeholders", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class LocalPlaceholderTests(unittest.TestCase):
    def test_creates_exact_filename_zero_byte_placeholder(self):
        module = load_module()
        with tempfile.TemporaryDirectory() as tmp:
            result = module.create_local_placeholder(tmp, "text_encoders", "qwen_3_8b_fp8mixed.safetensors")
            self.assertTrue(result["created"])
            self.assertEqual(result["size"], 0)
            self.assertTrue(Path(result["local_path"]).is_file())

    def test_preserves_existing_non_empty_file(self):
        module = load_module()
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "models" / "vae"
            target.mkdir(parents=True)
            file_path = target / "flux2-vae.safetensors"
            file_path.write_bytes(b"real-model")
            result = module.create_local_placeholder(tmp, "vae", "flux2-vae.safetensors")
            self.assertFalse(result["created"])
            self.assertTrue(result["existed"])
            self.assertEqual(result["size"], len(b"real-model"))

    def test_rejects_path_traversal(self):
        module = load_module()
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):
                module.create_local_placeholder(tmp, "text_encoders", "../evil.safetensors")

    def test_batch_creation_supports_requested_examples(self):
        module = load_module()
        with tempfile.TemporaryDirectory() as tmp:
            results = module.create_local_placeholders(tmp, [
                {"folder": "text_encoders", "filename": "qwen_3_8b_fp8mixed.safetensors"},
                {"folder": "diffusion_models", "filename": "flux-2-klein-9b-fp8.safetensors"},
                {"folder": "vae", "filename": "flux2-vae.safetensors"},
            ])
            self.assertEqual(len(results), 3)
            self.assertTrue(all(item["size"] == 0 for item in results))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests.test_local_placeholders -v`
Expected: FAIL because `local_placeholders.py` does not exist yet

### Task 2: Implement the pure placeholder helper

**Files:**
- Create: `local_placeholders.py`
- Test: `tests/test_local_placeholders.py`

- [ ] **Step 1: Write minimal implementation**

```python
import os
import re


ALLOWED_MODEL_FOLDERS = (
    "checkpoints",
    "diffusion_models",
    "unet",
    "loras",
    "vae",
    "controlnet",
    "upscale_models",
    "embeddings",
    "clip",
    "text_encoders",
    "model_patches",
    "clip_vision",
    "style_models",
    "vae_approx",
    "hypernetworks",
    "gligen",
    "photomaker",
    "latent_upscale_models",
    "audio_encoders",
    "frame_interpolation",
)


def create_local_placeholder(comfyui_root, folder, filename):
    ...


def create_local_placeholders(comfyui_root, items):
    ...
```

- [ ] **Step 2: Run test to verify it passes**

Run: `python -m unittest tests.test_local_placeholders -v`
Expected: PASS

### Task 3: Wire helper into backend routes

**Files:**
- Modify: `__init__.py`

- [ ] **Step 1: Import helper functions and allowed folders**

```python
from local_placeholders import (
    ALLOWED_MODEL_FOLDERS,
    create_local_placeholder,
    create_local_placeholders,
    get_local_model_file_info,
)
```

- [ ] **Step 2: Add backend glue helpers**

Implement small local functions in `__init__.py` to:

- normalize download/install payload folder values
- attach local file info to listed models
- summarize placeholder creation results for responses

- [ ] **Step 3: Update routes**

Add or modify:

- `POST /comfymodal/model/install`
- `POST /comfymodal/models/batch-install`
- `POST /comfymodal/models/inject`
- `POST /comfymodal/models/inject-all`
- `GET /comfymodal/models`

Required behaviors:

- validate `save_path`/`folder`
- create exact-name placeholders after successful downloads
- return placeholder metadata
- use remote `get_sync_status()` for inject-all so all remote model folders are covered
- preserve checkpoint-family `file.folder` behavior

- [ ] **Step 4: Run helper tests again**

Run: `python -m unittest tests.test_local_placeholders -v`
Expected: PASS

### Task 4: Restore sidebar placeholder UX

**Files:**
- Modify: `web/modal-settings.js`

- [ ] **Step 1: Add `unet` back to the download folder dropdown**

Keep grouped display intact, but include repo-supported `unet` in `DOWNLOAD_FOLDERS`.

- [ ] **Step 2: Show local placeholder status in the model list**

Use backend-provided `local_placeholder` info to show whether a row has:

- no local file
- zero-byte placeholder
- real local file

- [ ] **Step 3: Add explicit placeholder actions**

Restore:

- per-model “Create local placeholder” action
- visible “Create all missing placeholders” action in the Models section

- [ ] **Step 4: Update success/help messaging**

Add clear user-facing text:

- download success message includes placeholder creation result
- warning that placeholders only work in Modal/cloud mode
- refresh/restart reminder for stale dropdowns

### Task 5: Refresh docs and verify

**Files:**
- Modify: `README.md`
- Modify: `README.ko.md`

- [ ] **Step 1: Update placeholder wording**

Replace `modal-<filename>` references with exact-filename placeholder behavior and mention the inject-all action.

- [ ] **Step 2: Run verification commands**

Run: `python -m unittest tests.test_local_placeholders -v`
Expected: PASS

Run: `python -m py_compile __init__.py local_placeholders.py modal_client.py comfyapp.py`
Expected: no output, exit 0

- [ ] **Step 3: Check git diff**

Run: `git diff -- tests/test_local_placeholders.py local_placeholders.py __init__.py web/modal-settings.js README.md README.ko.md`
Expected: only focused placeholder-related changes

- [ ] **Step 4: Commit only if user requests it**

Do not create a git commit unless the user explicitly asks.
