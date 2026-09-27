# Modal Execution Optimization Phase 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make snapshot restore measurably cheap, add prompt-integrity guardrails, and reduce risky multi-prompt GPU execution without changing prompt semantics.

**Architecture:** Keep the subprocess ComfyUI backend and the current `/comfymodal/prompt` route. Add a small helper module for prompt hashing and model-stack extraction, tighten `comfyapp.py` startup/restore and localhost HTTP usage, and narrow the Modal GPU worker to one active prompt at a time. Async submit/cancel, snapshot versioning, and experimental in-process execution are intentionally deferred to later plans so this pass stays precise.

**Tech Stack:** Python 3.11, Modal, aiohttp routes in `__init__.py`, unittest, httpx.

**Repo policy note:** Do **not** create git commits as part of this plan unless the user later asks for them explicitly.

---

## File map

- Add: `workflow_metadata.py`
  - stable prompt hashing, prompt field summary extraction, read-only model-stack extraction helpers
- Modify: `__init__.py`
  - prompt-integrity instrumentation in `/comfymodal/prompt` and `_execute_job`
- Modify: `comfyapp.py`
  - startup/restore timing logs, cheap symlink restore, localhost HTTP client reuse, safe output URL encoding, single-prompt worker concurrency
- Modify: `tests/test_comfyapp_volume_lifecycle.py`
  - AST regressions for cheap `restore()` behavior
- Add: `tests/test_workflow_metadata.py`
  - pure helper tests for stable hashing, prompt field summary, and model-stack extraction
- Add: `tests/test_modal_worker_config.py`
  - AST checks that all Modal GPU classes use `target_inputs=1` and `max_inputs=1`

## Task 1: Lock in phase-1 behavior with failing tests

**Files:**
- Add: `tests/test_workflow_metadata.py`
- Add: `tests/test_modal_worker_config.py`
- Modify: `tests/test_comfyapp_volume_lifecycle.py`

- [ ] **Step 1: Add pure tests for prompt hashing and model-stack extraction**

Create `tests/test_workflow_metadata.py` with a small synthetic workflow that exercises prompt hashing, common numeric fields, and a FLUX-style base model stack.

```python
import unittest

from workflow_metadata import (
    extract_model_stack,
    prompt_sha256,
    summarize_prompt_fields,
)


WORKFLOW_A = {
    "3": {"class_type": "KSampler", "inputs": {
        "seed": 7, "steps": 20, "cfg": 3.5,
        "sampler_name": "euler", "scheduler": "normal", "denoise": 1,
    }},
    "4": {"class_type": "EmptyLatentImage", "inputs": {"width": 1024, "height": 1024}},
    "10": {"class_type": "UNETLoader", "inputs": {"unet_name": "flux-2-klein-9b-fp8.safetensors"}},
    "11": {"class_type": "CLIPLoader", "inputs": {"clip_name": "qwen_3_8b_fp8mixed.safetensors"}},
    "12": {"class_type": "VAELoader", "inputs": {"vae_name": "flux2-vae.safetensors"}},
}

WORKFLOW_B = {
    "12": WORKFLOW_A["12"],
    "11": WORKFLOW_A["11"],
    "10": WORKFLOW_A["10"],
    "4": WORKFLOW_A["4"],
    "3": WORKFLOW_A["3"],
}


class WorkflowMetadataTests(unittest.TestCase):
    def test_prompt_hash_is_stable_across_key_order(self):
        self.assertEqual(prompt_sha256(WORKFLOW_A), prompt_sha256(WORKFLOW_B))

    def test_prompt_summary_extracts_common_fields(self):
        summary = summarize_prompt_fields(WORKFLOW_A)
        self.assertEqual(summary["seed"], 7)
        self.assertEqual(summary["steps"], 20)
        self.assertEqual(summary["cfg"], 3.5)
        self.assertEqual(summary["width"], 1024)
        self.assertEqual(summary["height"], 1024)

    def test_extract_model_stack_collects_flux_base_stack(self):
        stack = extract_model_stack(WORKFLOW_A)
        self.assertIn("flux-2-klein-9b-fp8.safetensors", stack["unet"])
        self.assertIn("qwen_3_8b_fp8mixed.safetensors", stack["clip"])
        self.assertIn("flux2-vae.safetensors", stack["vae"])
```

- [ ] **Step 2: Add AST coverage for single-prompt Modal worker configuration**

Create `tests/test_modal_worker_config.py` so all three GPU classes must explicitly use `@modal.concurrent(target_inputs=1, max_inputs=1)`.

```python
import ast
import unittest
from pathlib import Path


COMFYAPP_PATH = Path(__file__).resolve().parents[1] / "comfyapp.py"


class ModalWorkerConfigTests(unittest.TestCase):
    def test_all_gpu_classes_use_single_prompt_concurrency(self):
        tree = ast.parse(COMFYAPP_PATH.read_text(encoding="utf-8"))
        targets = {"ComfyAPI", "ComfyAPI_A100", "ComfyAPI_T4"}
        found = {}
        for node in tree.body:
            if isinstance(node, ast.ClassDef) and node.name in targets:
                for deco in node.decorator_list:
                    if isinstance(deco, ast.Call) and getattr(deco.func, "attr", "") == "concurrent":
                        kwargs = {kw.arg: getattr(kw.value, "value", None) for kw in deco.keywords}
                        found[node.name] = kwargs
        self.assertEqual(found["ComfyAPI"]["target_inputs"], 1)
        self.assertEqual(found["ComfyAPI"]["max_inputs"], 1)
        self.assertEqual(found["ComfyAPI_A100"]["target_inputs"], 1)
        self.assertEqual(found["ComfyAPI_A100"]["max_inputs"], 1)
        self.assertEqual(found["ComfyAPI_T4"]["target_inputs"], 1)
        self.assertEqual(found["ComfyAPI_T4"]["max_inputs"], 1)
```

- [ ] **Step 3: Tighten the restore AST regression test**

Extend `tests/test_comfyapp_volume_lifecycle.py` so `_ComfyAPIMixin.restore()` no longer allows the heavy symlink-repair path.

```python
    def test_restore_does_not_use_heavy_filesystem_repairs(self):
        restore = _get_method("restore")
        forbidden = {
            ("shutil", "rmtree"),
            ("os", "symlink"),
        }
        seen = {
            (node.func.value.id, node.func.attr)
            for node in ast.walk(restore)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and isinstance(node.func.value, ast.Name)
        }
        self.assertTrue(forbidden.isdisjoint(seen), f"Found heavy restore calls: {seen & forbidden}")
```

- [ ] **Step 4: Run the targeted tests and verify they fail**

Run:

```powershell
python -m unittest tests.test_workflow_metadata tests.test_modal_worker_config tests.test_comfyapp_volume_lifecycle -v
```

Expected: failure because `workflow_metadata.py` does not exist yet, the worker decorators still use `max_inputs=4`, and `restore()` still uses the heavy symlink path.

## Task 2: Add a focused `workflow_metadata.py` helper module

**Files:**
- Add: `workflow_metadata.py`
- Test: `tests/test_workflow_metadata.py`

- [ ] **Step 1: Add stable prompt hashing helpers**

Create `workflow_metadata.py` with deterministic JSON serialization and hashing.

```python
import hashlib
import json


def _stable_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def prompt_sha256(prompt: dict) -> str:
    return hashlib.sha256(_stable_json(prompt).encode("utf-8")).hexdigest()
```

- [ ] **Step 2: Add prompt field summary extraction**

Use a conservative scan that records only fields already present in the workflow.

```python
SUMMARY_KEYS = {
    "cfg": "cfg",
    "steps": "steps",
    "seed": "seed",
    "sampler_name": "sampler",
    "scheduler": "scheduler",
    "denoise": "denoise",
    "width": "width",
    "height": "height",
}


def summarize_prompt_fields(prompt: dict) -> dict:
    summary = {}
    for node in prompt.values():
        if not isinstance(node, dict):
            continue
        inputs = node.get("inputs", {})
        if not isinstance(inputs, dict):
            continue
        for src, dest in SUMMARY_KEYS.items():
            if src in inputs and dest not in summary:
                summary[dest] = inputs[src]
    return summary
```

- [ ] **Step 3: Add read-only model-stack extraction**

Implement a small mapping for the base stack types we explicitly care about now.

```python
MODEL_INPUTS = {
    "CheckpointLoaderSimple": ("checkpoint", "ckpt_name"),
    "CheckpointLoader": ("checkpoint", "ckpt_name"),
    "UNETLoader": ("unet", "unet_name"),
    "CLIPLoader": ("clip", "clip_name"),
    "VAELoader": ("vae", "vae_name"),
    "LoraLoader": ("lora", "lora_name"),
    "LoraLoaderModelOnly": ("lora", "lora_name"),
    "ControlNetLoader": ("controlnet", "control_net_name"),
}


def extract_model_stack(prompt: dict) -> dict:
    stack = {key: [] for key, _ in MODEL_INPUTS.values()}
    for node in prompt.values():
        if not isinstance(node, dict):
            continue
        class_type = node.get("class_type")
        if class_type not in MODEL_INPUTS:
            continue
        bucket, input_key = MODEL_INPUTS[class_type]
        value = node.get("inputs", {}).get(input_key)
        if isinstance(value, str) and value and value not in stack[bucket]:
            stack[bucket].append(value)
    return stack
```

- [ ] **Step 4: Run the helper tests and keep the remaining regressions red**

Run:

```powershell
python -m unittest tests.test_workflow_metadata tests.test_modal_worker_config tests.test_comfyapp_volume_lifecycle -v
```

Expected: `tests.test_workflow_metadata` passes, while worker-config and restore AST tests still fail.

## Task 3: Wire prompt-integrity and read-only model-stack tracking into `__init__.py`

**Files:**
- Modify: `__init__.py`
- Modify: `workflow_metadata.py`
- Test: `tests/test_workflow_metadata.py`

- [ ] **Step 1: Import the new helper functions and add module-level state**

Near the existing imports in `__init__.py`, add the helper imports and a tiny last-success cache.

```python
from workflow_metadata import extract_model_stack, prompt_sha256, summarize_prompt_fields


_last_successful_model_stack: dict = {}
```

- [ ] **Step 2: Capture prompt-integrity metadata in `/comfymodal/prompt`**

Update `modal_prompt()` so the queue item carries prompt hashes and summaries without mutating the workflow.

```python
        local_payload_hash = prompt_sha256(body)
        workflow_hash = prompt_sha256(workflow)
        prompt_summary = summarize_prompt_fields(workflow)
        model_stack = extract_model_stack(workflow)
        extra_data = {
            "client_id": client_id,
            "create_time": int(time.time() * 1000),
            "local_payload_hash": local_payload_hash,
            "workflow_hash": workflow_hash,
            "prompt_summary": prompt_summary,
            "model_stack": model_stack,
        }
```

- [ ] **Step 3: Verify the workflow hash before the remote call and record the last successful model stack**

Add a guard at the start of `_execute_job()` just before `run_prompt(workflow, input_images)`.

```python
        expected_hash = extra_data.get("workflow_hash")
        actual_hash = prompt_sha256(workflow)
        if expected_hash and actual_hash != expected_hash:
            raise RuntimeError(
                f"Prompt integrity violation: expected {expected_hash[:12]}, got {actual_hash[:12]}"
            )
        print(
            f"[comfyui-modal] prompt_hash={actual_hash[:12]} fields={extra_data.get('prompt_summary', {})}"
        )
        result = await run_prompt(workflow, input_images)
        _last_successful_model_stack.clear()
        _last_successful_model_stack.update(extra_data.get("model_stack", {}))
```

- [ ] **Step 4: Run the targeted suite again**

Run:

```powershell
python -m unittest tests.test_workflow_metadata tests.test_modal_worker_config tests.test_comfyapp_volume_lifecycle -v
```

Expected: prompt metadata tests still pass; restore and worker-config tests are still red until `comfyapp.py` is updated.

## Task 4: Make `comfyapp.py` restore cheap and localhost I/O explicit

**Files:**
- Modify: `comfyapp.py`
- Test: `tests/test_comfyapp_volume_lifecycle.py`

- [ ] **Step 1: Add a tiny helper for the models symlink and lifecycle logs**

Add a focused helper above `startup()`/`restore()`.

```python
    def _ensure_models_symlink(self):
        comfy_models = "/root/comfy/ComfyUI/models"
        try:
            os.symlink(MODELS_PATH, comfy_models)
        except FileExistsError:
            return

    def _log_lifecycle(self, stage: str, started: float):
        print(f"[comfyapp] lifecycle={stage} duration_s={time.time() - started:.3f}")
```

Use it like:

```python
    @modal.enter(snap=True)
    def startup(self):
        started = time.time()
        print("[comfyapp] lifecycle=startup snap=True")
        self._ensure_models_symlink()
        _, self._custom_nodes_state = self._sync_custom_nodes_from_volume()
        install_summary = self._install_custom_node_requirements()
        self._record_runtime_state()
        self._restart_comfy()
        self._log_lifecycle("startup", started)
```

- [ ] **Step 2: Make `restore()` O(1) and observable**

Replace the current heavy symlink-repair block with a cheap best-effort call and lifecycle log.

```python
    @modal.enter(snap=False)
    def restore(self):
        started = time.time()
        print("[comfyapp] lifecycle=restore snap=False")
        self._ensure_models_symlink()
        self._log_lifecycle("restore", started)
```

- [ ] **Step 3: Add a small reusable localhost HTTP client and safe output query encoding**

Keep the change local to `_ComfyAPIMixin`.

```python
    def _http_client(self):
        import httpx
        client = getattr(self, "_client", None)
        if client is None:
            client = httpx.Client(base_url=f"http://127.0.0.1:{COMFYUI_API_PORT}", timeout=30.0)
            self._client = client
        return client
```

Use it in `_wait_for_comfy`, `object_info`, `run_prompt`, `_poll_until_done`, and `_collect_outputs`, and build `/view` query strings with `urllib.parse.urlencode`:

```python
from urllib.parse import urlencode

params = urlencode({
    "filename": img["filename"],
    "subfolder": img.get("subfolder", ""),
    "type": img.get("type", "output"),
})
url = f"/view?{params}"
```

- [ ] **Step 4: Close the cached HTTP client on shutdown**

```python
    @modal.exit()
    def shutdown(self):
        client = getattr(self, "_client", None)
        if client is not None:
            client.close()
        if self._proc and self._proc.poll() is None:
            self._proc.terminate()
            try:
                self._proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self._proc.kill()
```

- [ ] **Step 5: Run the restore regression tests**

Run:

```powershell
python -m unittest tests.test_comfyapp_volume_lifecycle -v
```

Expected: the restore AST tests now pass.

## Task 5: Narrow each GPU worker to a single active prompt and verify the full phase-1 slice

**Files:**
- Modify: `comfyapp.py`
- Test: `tests/test_modal_worker_config.py`
- Test: `tests/test_workflow_metadata.py`
- Test: `tests/test_comfyapp_volume_lifecycle.py`
- Test: `tests/test_comfyapp_runtime_state.py`
- Test: `tests/test_modal_runtime_routes.py`

- [ ] **Step 1: Change the three Modal worker decorators to single-prompt execution**

Update the decorators at the bottom of `comfyapp.py`.

```python
@modal.concurrent(target_inputs=1, max_inputs=1)
class ComfyAPI(_ComfyAPIMixin):
    pass

@modal.concurrent(target_inputs=1, max_inputs=1)
class ComfyAPI_A100(_ComfyAPIMixin):
    pass

@modal.concurrent(target_inputs=1, max_inputs=1)
class ComfyAPI_T4(_ComfyAPIMixin):
    pass
```

- [ ] **Step 2: Run the targeted phase-1 suite**

Run:

```powershell
python -m unittest tests.test_workflow_metadata tests.test_modal_worker_config tests.test_comfyapp_volume_lifecycle tests.test_comfyapp_runtime_state tests.test_modal_runtime_routes -v
```

Expected: PASS.

- [ ] **Step 3: Run the broader repository suite as a regression check**

Run:

```powershell
python -m unittest discover -s tests -p "test_*.py" -v
```

Expected: PASS.

- [ ] **Step 4: Verify the implementation matches the phase-1 performance validation goals**

After tests are green, confirm the code now emits these logs on container lifecycle paths:

```text
[comfyapp] lifecycle=startup snap=True
[comfyapp] lifecycle=restore snap=False
```

And ensure the code now has:

- prompt hash capture at `/comfymodal/prompt`
- prompt hash verification before the Modal remote call
- read-only last-successful model-stack tracking
- `restore()` with no `shutil.rmtree()` and no heavy sync/reload calls
- `@modal.concurrent(target_inputs=1, max_inputs=1)` on all GPU worker classes
