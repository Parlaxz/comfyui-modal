# Stale Warmup Profile Prevention Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make cold restore warm the workflow that is about to run, or disable warmup safely when that workflow cannot be identified confidently.

**Architecture:** Move warmup-profile derivation into shared workflow metadata helpers so both the local bridge and Modal runtime compute the same stack/profile shape. Add a CPU-only active-next-profile setter before dispatch, then change restore to prefer that explicit activation over env defaults and never infer intent from `last_stack` again.

**Tech Stack:** Python 3.11, Modal function/class APIs, ComfyUI custom node runtime, `unittest`, JSON volume-backed runtime config.

---

## File map

- Modify: `workflow_metadata.py` — shared warmup-stack extraction and profile conversion helpers for both local and Modal code paths.
- Modify: `tests/test_workflow_metadata.py` — regression tests for shared stack/profile derivation.
- Modify: `comfyapp.py` — active-next-profile persistence, CPU-only setter, restore-time selection order, restore/prompt diagnostics.
- Modify: `modal_client.py` — async client wrapper for the new CPU-only setter.
- Modify: `__init__.py` — pre-dispatch activation payload builder and `_execute_job()` setter call.
- Modify: `tests/test_comfyapp_auto_warmup.py` — active-next-profile persistence/selection tests and AST assertions for restore behavior.
- Modify: `tests/test_modal_client_gpu_config.py` — modal client wrapper test for the new setter.
- Modify: `tests/test_modal_runtime_routes.py` — AST-level presence test for the new client function.
- Modify: `tests/test_restore_timing_data_flow.py` — local activation helper and `_execute_job()` ordering tests.

### Task 1: Share warmup-profile derivation logic

**Files:**
- Modify: `workflow_metadata.py:1-85`
- Modify: `tests/test_workflow_metadata.py:1-50`

- [ ] **Step 1: Write the failing test**

Add these tests to `tests/test_workflow_metadata.py`:

```python
import unittest

from workflow_metadata import (
    extract_model_stack,
    extract_warmup_stack,
    normalize_flux_clip_pair,
    prompt_sha256,
    stack_to_warmup_profile,
    summarize_prompt_fields,
    warmup_profile_matches_stack,
)


WORKFLOW_DUAL_CLIP = {
    "10": {"class_type": "UNETLoader", "inputs": {"unet_name": "flux-2-klein-base-9b-fp8.safetensors"}},
    "11": {"class_type": "DualCLIPLoader", "inputs": {
        "clip_name1": "t5xxl_fp16.safetensors",
        "clip_name2": "clip_l.safetensors",
        "type": "flux",
    }},
    "12": {"class_type": "VAELoader", "inputs": {"vae_name": "full_encoder_small_decoder.safetensors"}},
}


class WorkflowMetadataTests(unittest.TestCase):
    def test_extract_warmup_stack_collects_dual_clip_and_clip_type(self):
        stack = extract_warmup_stack(WORKFLOW_DUAL_CLIP)
        self.assertEqual(stack["unet"], ["flux-2-klein-base-9b-fp8.safetensors"])
        self.assertEqual(stack["clip"], ["t5xxl_fp16.safetensors", "clip_l.safetensors"])
        self.assertEqual(stack["vae"], ["full_encoder_small_decoder.safetensors"])
        self.assertEqual(stack["clip_type"], "flux")

    def test_stack_to_warmup_profile_normalizes_flux_clip_order(self):
        profile = stack_to_warmup_profile(extract_warmup_stack(WORKFLOW_DUAL_CLIP))
        self.assertEqual(profile, {
            "mode": "split",
            "unet": "flux-2-klein-base-9b-fp8.safetensors",
            "clip1": "clip_l.safetensors",
            "clip2": "t5xxl_fp16.safetensors",
            "vae": "full_encoder_small_decoder.safetensors",
            "clip_type": "flux",
        })

    def test_warmup_profile_matches_stack_returns_false_for_switched_workflow(self):
        requested = extract_warmup_stack(WORKFLOW_DUAL_CLIP)
        stale = {
            "mode": "split",
            "unet": "flux2_dev_fp8mixed.safetensors",
            "clip1": "clip_l.safetensors",
            "clip2": "mistral_3_small_flux2_bf16.safetensors",
            "vae": "full_encoder_small_decoder.safetensors",
            "clip_type": "flux",
        }
        self.assertFalse(warmup_profile_matches_stack(stale, requested))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests.test_workflow_metadata -v`
Expected: FAIL with `ImportError` or `AttributeError` because `extract_warmup_stack`, `stack_to_warmup_profile`, or `warmup_profile_matches_stack` do not exist yet.

- [ ] **Step 3: Write minimal implementation**

Update `workflow_metadata.py` to add shared warmup helpers without breaking the existing `extract_model_stack()` API:

```python
"""Deterministic prompt hashing, field summary extraction, and model-stack extraction."""

import hashlib
import json

_LOADER_MAPPINGS: dict[str, tuple[str, str]] = {
    "CheckpointLoaderSimple": ("checkpoint", "ckpt_name"),
    "CheckpointLoader": ("checkpoint", "ckpt_name"),
    "UNETLoader": ("unet", "unet_name"),
    "CLIPLoader": ("clip", "clip_name"),
    "VAELoader": ("vae", "vae_name"),
    "LoraLoader": ("lora", "lora_name"),
    "LoraLoaderModelOnly": ("lora", "lora_name"),
    "ControlNetLoader": ("controlnet", "control_net_name"),
}


def normalize_flux_clip_pair(clip1: str, clip2: str) -> tuple[str, str]:
    a = clip1.lower()
    b = clip2.lower()
    a_is_t5 = "t5" in a
    b_is_clip_l = "clip_l" in b or "clip-l" in b or "clip-vit" in b
    if a_is_t5 and b_is_clip_l:
        return clip2, clip1
    return clip1, clip2


def extract_warmup_stack(prompt: dict) -> dict:
    stack: dict = {"checkpoint": [], "unet": [], "clip": [], "vae": [], "clip_type": "flux"}
    for node in prompt.values():
        if not isinstance(node, dict):
            continue
        class_type = node.get("class_type", "")
        inputs = node.get("inputs", {})
        if not isinstance(inputs, dict):
            continue
        if class_type in {"CheckpointLoaderSimple", "CheckpointLoader"}:
            value = inputs.get("ckpt_name")
            if isinstance(value, str) and value and value not in stack["checkpoint"]:
                stack["checkpoint"].append(value)
        elif class_type == "UNETLoader":
            value = inputs.get("unet_name")
            if isinstance(value, str) and value and value not in stack["unet"]:
                stack["unet"].append(value)
        elif class_type == "DualCLIPLoader":
            for key in ("clip_name1", "clip_name2"):
                value = inputs.get(key)
                if isinstance(value, str) and value and value not in stack["clip"]:
                    stack["clip"].append(value)
            clip_type = inputs.get("type", "")
            if isinstance(clip_type, str) and clip_type:
                stack["clip_type"] = clip_type
        elif class_type == "CLIPLoader":
            value = inputs.get("clip_name")
            if isinstance(value, str) and value and value not in stack["clip"]:
                stack["clip"].append(value)
            clip_type = inputs.get("type", "")
            if isinstance(clip_type, str) and clip_type:
                stack["clip_type"] = clip_type
        elif class_type == "VAELoader":
            value = inputs.get("vae_name")
            if isinstance(value, str) and value and value not in stack["vae"]:
                stack["vae"].append(value)
    return stack


def stack_to_warmup_profile(stack: dict) -> dict:
    if stack.get("checkpoint"):
        return {"mode": "checkpoint", "checkpoint": stack["checkpoint"][0]}
    if stack.get("unet") and stack.get("clip") and stack.get("vae"):
        clips = stack["clip"]
        clip1, clip2 = normalize_flux_clip_pair(clips[0], clips[-1] if len(clips) > 1 else clips[0])
        return {
            "mode": "split",
            "unet": stack["unet"][0],
            "clip1": clip1,
            "clip2": clip2,
            "vae": stack["vae"][0],
            "clip_type": stack.get("clip_type", "flux"),
        }
    return {}


def warmup_profile_matches_stack(profile: dict, requested: dict) -> bool:
    if not profile:
        return True
    mode = profile.get("mode")
    if mode == "checkpoint":
        checkpoint = profile.get("checkpoint", "")
        return bool(checkpoint) and checkpoint in requested.get("checkpoint", [])
    if mode == "split":
        return (
            profile.get("unet", "") in requested.get("unet", [])
            and profile.get("clip1", "") in requested.get("clip", [])
            and profile.get("clip2", "") in requested.get("clip", [])
            and profile.get("vae", "") in requested.get("vae", [])
        )
    return False
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m unittest tests.test_workflow_metadata -v`
Expected: PASS, including the new dual-CLIP/profile-match coverage.

- [ ] **Step 5: Commit**

```bash
git add workflow_metadata.py tests/test_workflow_metadata.py
git commit -m "refactor: share warmup profile derivation helpers"
```

### Task 2: Add active-next profile storage and CPU-only setter

**Files:**
- Modify: `comfyapp.py:760-765, 1045-1147, 1457-1614`
- Modify: `modal_client.py:24-29, 217-224`
- Modify: `tests/test_comfyapp_auto_warmup.py:133-205, 308-361`
- Modify: `tests/test_modal_client_gpu_config.py:90-125`
- Modify: `tests/test_modal_runtime_routes.py:15-33`

- [ ] **Step 1: Write the failing test**

Add these tests to `tests/test_comfyapp_auto_warmup.py`:

```python
class SaveLoadActiveProfileTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mktemp(suffix=".json")
        import comfyapp
        comfyapp.ACTIVE_NEXT_PROFILE_PATH = self.tmp
        comfyapp.ACTIVE_NEXT_PROFILE_TTL_S = 60

    def tearDown(self):
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
        inst._write_active_next_profile(payload)
        self.assertEqual(inst._load_active_next_profile(now=1001.0)["profile_token"], "tok-1")

    def test_load_active_profile_returns_empty_when_expired(self):
        inst = self._make_instance()
        inst._write_active_next_profile({
            "profile_token": "tok-expired",
            "workflow_hash": "hash-old",
            "created_at": 1000.0,
            "expires_at": 1001.0,
            "disable_warmup": False,
            "model_stack": {},
            "warmup_profile": {"mode": "checkpoint", "checkpoint": "old.safetensors"},
        })
        self.assertEqual(inst._load_active_next_profile(now=1002.0), {})


class SnapshotPreloadProfileTests(unittest.TestCase):
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
```

Add this client wrapper test to `tests/test_modal_client_gpu_config.py`:

```python
    def test_set_active_warmup_profile_calls_modal_function(self):
        calls = []

        class FakeFunctionRemote:
            def remote(self, payload):
                calls.append(payload)
                return {"status": "ok", "payload": payload}

        fake_modal = ModuleType("modal")
        setattr(fake_modal, "Cls", SimpleNamespace(from_name=lambda app, cls: lambda: f"{app}:{cls}"))
        setattr(
            fake_modal,
            "Function",
            SimpleNamespace(from_name=lambda app, fn: SimpleNamespace(remote=FakeFunctionRemote().remote)),
        )
        sys.modules["modal"] = fake_modal
        sys.modules.pop("modal_client", None)
        mod = importlib.import_module("modal_client")

        payload = {"profile_token": "tok-1", "workflow_hash": "hash-1"}
        result = asyncio.run(mod.set_active_warmup_profile(payload))

        self.assertEqual(calls, [payload])
        self.assertEqual(result["status"], "ok")
```

Add this AST check to `tests/test_modal_runtime_routes.py`:

```python
    def test_set_active_warmup_profile_defined_in_modal_client(self):
        source = MODAL_CLIENT_PATH.read_text(encoding="utf-8")
        tree = ast.parse(source)
        funcs = {n.name for n in ast.walk(tree) if isinstance(n, ast.AsyncFunctionDef)}
        self.assertIn("set_active_warmup_profile", funcs)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests.test_comfyapp_auto_warmup tests.test_modal_client_gpu_config tests.test_modal_runtime_routes -v`
Expected: FAIL because the active-next helpers and `modal_client.set_active_warmup_profile()` do not exist yet.

- [ ] **Step 3: Write minimal implementation**

In `comfyapp.py`, add the new constants near the existing volume paths:

```python
ACTIVE_NEXT_PROFILE_PATH = "/root/models/runtime_config/active_next_profile.json"
ACTIVE_NEXT_PROFILE_TTL_S = 60
```

Add these `_ComfyAPIMixin` helpers near `_save_last_model_stack()` / `_load_last_model_stack()`:

```python
    def _write_active_next_profile(self, payload: dict) -> None:
        try:
            os.makedirs(os.path.dirname(ACTIVE_NEXT_PROFILE_PATH), exist_ok=True)
            tmp_path = f"{ACTIVE_NEXT_PROFILE_PATH}.tmp"
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(payload, f, indent=2, sort_keys=True)
            os.replace(tmp_path, ACTIVE_NEXT_PROFILE_PATH)
            vol.commit()
        except Exception as exc:
            print(f"[comfyapp] failed to write active next profile: {exc}")
            raise

    def _load_active_next_profile(self, now: float | None = None) -> dict:
        try:
            if not os.path.isfile(ACTIVE_NEXT_PROFILE_PATH):
                return {}
            with open(ACTIVE_NEXT_PROFILE_PATH, "r", encoding="utf-8") as f:
                payload = json.load(f)
            if not isinstance(payload, dict) or not payload:
                return {}
            current = time.time() if now is None else now
            expires_at = float(payload.get("expires_at", 0) or 0)
            if expires_at and current > expires_at:
                print(f"[comfyapp] active_next_profile expired token={payload.get('profile_token','?')} now={current} expires_at={expires_at}")
                return {}
            return payload
        except (json.JSONDecodeError, OSError, ValueError, TypeError) as exc:
            print(f"[comfyapp] failed to load active next profile: {exc}")
            return {}
```

Replace the body of `_snapshot_preload_profile()` with explicit-activation-first logic:

```python
    def _snapshot_preload_profile(self) -> dict:
        active = self._load_active_next_profile()
        env_profile = load_warmup_profile()
        profile = None
        source = "none"
        if active:
            if active.get("disable_warmup"):
                print(
                    f"[comfyapp] snapshot_preload_profile source=active_next_profile profile_token={active.get('profile_token','?')} disable_warmup=1"
                )
                return None
            profile = dict(active.get("warmup_profile") or {})
            source = "active_next_profile"
            if profile:
                profile["_source"] = source
                profile["_profile_token"] = active.get("profile_token", "")
                profile["_workflow_hash"] = active.get("workflow_hash", "")
                profile["_current_workflow_stack"] = dict(active.get("model_stack") or {})
                print(
                    f"[comfyapp] snapshot_preload_profile source={source} profile_token={profile.get('_profile_token','')} workflow_hash={profile.get('_workflow_hash','')} data={profile}"
                )
                return profile
        if env_profile:
            profile = dict(env_profile)
            profile["_source"] = "env_default"
            print(f"[comfyapp] snapshot_preload_profile source=env_default mode={profile.get('mode','?')} data={profile}")
            return profile
        print("[comfyapp] snapshot_preload_profile source=none - no warmup profile configured")
        return None
```

Add the new CPU-only Modal function near the other setters:

```python
@app.function(
    image=modal.Image.debian_slim(python_version="3.11")
    .add_local_python_source("gpu_catalog")
    .add_local_python_source("timing_trace"),
    cpu=1,
    memory=512,
    timeout=30,
    volumes={MODELS_PATH: vol},
)
def set_active_warmup_profile(payload: dict) -> dict:
    os.makedirs(RUNTIME_CONFIG_DIR, exist_ok=True)
    profile = dict(payload or {})
    tmp_path = f"{ACTIVE_NEXT_PROFILE_PATH}.tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(profile, f, indent=2, sort_keys=True)
    os.replace(tmp_path, ACTIVE_NEXT_PROFILE_PATH)
    vol.commit()
    print(
        f"[comfyapp] set_active_warmup_profile token={profile.get('profile_token','')} "
        f"workflow_hash={profile.get('workflow_hash','')} disable_warmup={1 if profile.get('disable_warmup') else 0}"
    )
    return {"status": "ok", "profile_token": profile.get("profile_token", "")}
```

In `modal_client.py`, add the Modal function handle and wrapper:

```python
_set_active_warmup_profile_fn = modal.Function.from_name("comfyui", "set_active_warmup_profile")


@_modal_error_handler
async def set_active_warmup_profile(payload: dict) -> dict:
    return await asyncio.to_thread(lambda: _set_active_warmup_profile_fn.remote(payload))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m unittest tests.test_comfyapp_auto_warmup tests.test_modal_client_gpu_config tests.test_modal_runtime_routes -v`
Expected: PASS, proving the persistence helpers, selection precedence, and client wrapper exist.

- [ ] **Step 5: Commit**

```bash
git add comfyapp.py modal_client.py tests/test_comfyapp_auto_warmup.py tests/test_modal_client_gpu_config.py tests/test_modal_runtime_routes.py
git commit -m "feat: add explicit next warmup profile activation"
```

### Task 3: Arm the active-next profile before dispatch

**Files:**
- Modify: `__init__.py:26, 299-323, 543-593, 725-731, 790-808`
- Modify: `tests/test_restore_timing_data_flow.py:21-178`

- [ ] **Step 1: Write the failing test**

Add these tests to `tests/test_restore_timing_data_flow.py`:

```python
import asyncio
import unittest
from unittest.mock import AsyncMock, MagicMock, patch


class TestRestoreTimingDataFlow(unittest.TestCase):
    def test_build_next_warmup_activation_returns_disable_for_unknown_stack(self):
        from __init__ import _build_next_warmup_activation

        payload = _build_next_warmup_activation({"3": {"class_type": "KSampler", "inputs": {}}}, "hash-unknown")

        self.assertEqual(payload["workflow_hash"], "hash-unknown")
        self.assertTrue(payload["disable_warmup"])
        self.assertEqual(payload["warmup_profile"], {})
        self.assertIn("profile_token", payload)

    def test_build_next_warmup_activation_builds_split_profile_for_known_stack(self):
        from __init__ import _build_next_warmup_activation

        workflow = {
            "10": {"class_type": "UNETLoader", "inputs": {"unet_name": "flux-2-klein-base-9b-fp8.safetensors"}},
            "11": {"class_type": "CLIPLoader", "inputs": {"clip_name": "qwen_3_8b_fp8mixed.safetensors", "type": "flux"}},
            "12": {"class_type": "VAELoader", "inputs": {"vae_name": "full_encoder_small_decoder.safetensors"}},
        }
        payload = _build_next_warmup_activation(workflow, "hash-known")

        self.assertFalse(payload["disable_warmup"])
        self.assertEqual(payload["warmup_profile"]["unet"], "flux-2-klein-base-9b-fp8.safetensors")
        self.assertEqual(payload["warmup_profile"]["vae"], "full_encoder_small_decoder.safetensors")

    def test_execute_job_arms_active_warmup_before_stream(self):
        from __init__ import _execute_job

        item = (
            1,
            "prompt-1",
            {"10": {"class_type": "UNETLoader", "inputs": {"unet_name": "u.safetensors"}}, "11": {"class_type": "CLIPLoader", "inputs": {"clip_name": "c.safetensors"}}, "12": {"class_type": "VAELoader", "inputs": {"vae_name": "v.safetensors"}}},
            {"client_id": "test", "workflow_hash": "hash-1", "prompt_summary": {}, "model_stack": {}, "trace": {}, "gpu": "a10g"},
            [],
            {},
        )

        calls = []

        async def fake_set_active(payload):
            calls.append(("set", payload["workflow_hash"], payload["disable_warmup"]))
            return {"status": "ok"}

        async def fake_stream(*args, **kwargs):
            calls.append(("stream", kwargs.get("gpu")))
            yield {"type": "result", "data": {"images": [], "videos": [], "trace": {"stages": {}}, "_restore_timing": {}}}

        fake_pq = self.fake_pq
        fake_pq.currently_running[1] = item

        with patch("__init__._pq", return_value=fake_pq), \
             patch("__init__._send", return_value=None), \
             patch("__init__._collect_input_images", return_value={}), \
             patch("__init__.set_active_warmup_profile", side_effect=fake_set_active), \
             patch("__init__.run_prompt_stream", side_effect=fake_stream), \
             patch("builtins.print", return_value=None):
            asyncio.run(_execute_job(item, 1))

        self.assertEqual(calls[0][0], "set")
        self.assertEqual(calls[1][0], "stream")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests.test_restore_timing_data_flow -v`
Expected: FAIL because `_build_next_warmup_activation()` does not exist and `_execute_job()` does not call `set_active_warmup_profile()` yet.

- [ ] **Step 3: Write minimal implementation**

Update the import and fallback wiring in `__init__.py` so the new client wrapper is available:

```python
from workflow_metadata import (
    extract_model_stack,
    extract_warmup_stack,
    prompt_sha256,
    stack_to_warmup_profile,
    summarize_prompt_fields,
)

from modal_client import (
    run_prompt,
    run_prompt_stream,
    get_object_info,
    health_check,
    download_model,
    batch_download_models,
    list_models,
    delete_model,
    set_gpu,
    get_gpu,
    get_default_gpu,
    get_available_gpus,
    sync_custom_nodes,
    refresh_custom_nodes,
    get_sync_status,
    upload_model_to_volume,
    upload_model_chunk,
    clear_cache,
    resync_runtime,
    get_runtime_state,
    set_active_warmup_profile,
)
```

Add this helper near `_execute_job()`:

```python
def _build_next_warmup_activation(workflow: dict, workflow_hash: str) -> dict:
    stack = extract_warmup_stack(workflow) if isinstance(workflow, dict) else {}
    profile = stack_to_warmup_profile(stack)
    now = time.time()
    return {
        "profile_token": str(uuid.uuid4()),
        "workflow_hash": workflow_hash,
        "created_at": now,
        "expires_at": now + 60.0,
        "mode": profile.get("mode", "none") if profile else "none",
        "model_stack": stack,
        "warmup_profile": profile,
        "disable_warmup": not bool(profile),
        "selected_at": None,
    }
```

Then arm the activation immediately before `run_prompt_stream()` inside `_execute_job()`:

```python
        activation_payload = _build_next_warmup_activation(workflow, prompt_hash)
        try:
            activation_result = await set_active_warmup_profile(activation_payload)
            print(
                f"[comfyui-modal] Armed active warmup profile token={activation_payload['profile_token']} "
                f"workflow_hash={prompt_hash[:12]} disable_warmup={1 if activation_payload['disable_warmup'] else 0} result={activation_result}"
            )
        except Exception as exc:
            print(f"[comfyui-modal] Failed to arm active warmup profile for {prompt_hash[:12]}: {exc}")

        remote_started = time.time()
        trace.mark("t2_local_dispatch")
```

Also add a stub in the modal-not-installed fallback block:

```python
def set_active_warmup_profile(*a, **kw): raise RuntimeError("modal not installed")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m unittest tests.test_restore_timing_data_flow -v`
Expected: PASS, including proof that the setter is called before `run_prompt_stream()`.

- [ ] **Step 5: Commit**

```bash
git add __init__.py tests/test_restore_timing_data_flow.py
git commit -m "feat: arm next warmup profile before dispatch"
```

### Task 4: Switch restore selection and mismatch diagnostics to explicit activation

**Files:**
- Modify: `comfyapp.py:1573-1657, 4153-4167, 4657-4673, 4846-4852`
- Modify: `tests/test_comfyapp_auto_warmup.py:315-361, 550-659`

- [ ] **Step 1: Write the failing test**

Add these tests to `tests/test_comfyapp_auto_warmup.py`:

```python
class SnapshotPreloadProfileTests(unittest.TestCase):
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


class AutoWarmupASTTests(unittest.TestCase):
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests.test_comfyapp_auto_warmup -v`
Expected: FAIL because `_snapshot_preload_profile()` still prefers `last_stack` and `run_prompt()` does not log the new explicit match fields.

- [ ] **Step 3: Write minimal implementation**

Update `comfyapp.py` restore logging around the early profile resolution section:

```python
        if ENABLE_WARMUP:
            _s = time.time()
            _warmup_profile = self._snapshot_preload_profile()
            if _warmup_profile:
                _warmup_paths = self._snapshot_preload_paths(_warmup_profile)
            __stages["early_path_resolve_ms"] = self._profile_ms(_s)
            print(
                f"[comfyapp] restore warmup selection current_workflow_stack={_warmup_profile.get('_current_workflow_stack', {}) if _warmup_profile else {}} "
                f"selected_warmup_profile={_warmup_profile or {}} profile_source={_warmup_profile.get('_source', 'none') if _warmup_profile else 'none'} "
                f"workflow_hash={_warmup_profile.get('_workflow_hash', '') if _warmup_profile else ''} "
                f"profile_token={_warmup_profile.get('_profile_token', '') if _warmup_profile else ''}"
            )
```

Update the subprocess `run_prompt()` diagnostics so they compare against the profile selected during restore, not just current env vars:

```python
        requested_stack = extract_requested_model_stack(workflow)
        selected_profile = dict((getattr(self, "_last_restore_timing", None) or {}).get("warmup_profile") or {})
        if not selected_profile:
            selected_profile = self._snapshot_preload_profile() or {}
        warmup_match = warmup_profile_matches_workflow(selected_profile, requested_stack)
        print(
            f"[comfyapp.profile] WARMUP_PROFILE_MATCH={'true' if warmup_match else 'false'} "
            f"profile_source={selected_profile.get('_source', 'none')} "
            f"profile_token={selected_profile.get('_profile_token', '')} workflow_hash={selected_profile.get('_workflow_hash', '')} "
            f"requested={requested_stack} profile={selected_profile}"
        )
```

Update the in-process path similarly at the existing post-run diagnostic block:

```python
            selected_profile = dict((_rt.get("warmup_profile") or {}))
            match_info = self._log_warmup_vs_workflow_diagnostics(selected_profile, requested_stack, raw_workflow=workflow)
            print(
                f"[comfyapp.profile] WARMUP_PROFILE_MATCH={'true' if all(v is not False for v in match_info.get('match', {}).values()) else 'false'} "
                f"profile_source={selected_profile.get('_source', 'none')} profile_token={selected_profile.get('_profile_token', '')} "
                f"workflow_hash={selected_profile.get('_workflow_hash', '')}"
            )
```

Finally, when building `_last_restore_timing`, preserve the actual restore-selected profile object so the later comparison can reuse it:

```python
        self._last_restore_timing = {
            **__stages,
            "warmup_profile": _warmup_profile or {},
            "warmup_profile_source": (_warmup_profile or {}).get("_source", "none"),
            "warmup_profile_token": (_warmup_profile or {}).get("_profile_token", ""),
        }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m unittest tests.test_comfyapp_auto_warmup -v`
Expected: PASS, proving restore no longer uses `last_stack` as a selector and both execution paths emit explicit match logs.

- [ ] **Step 5: Commit**

```bash
git add comfyapp.py tests/test_comfyapp_auto_warmup.py
git commit -m "fix: select warmup profile from explicit next activation"
```

### Task 5: Run the focused regression suite

**Files:**
- Modify: `comfyapp.py`
- Modify: `workflow_metadata.py`
- Modify: `modal_client.py`
- Modify: `__init__.py`
- Modify: `tests/test_workflow_metadata.py`
- Modify: `tests/test_comfyapp_auto_warmup.py`
- Modify: `tests/test_modal_client_gpu_config.py`
- Modify: `tests/test_modal_runtime_routes.py`
- Modify: `tests/test_restore_timing_data_flow.py`

- [ ] **Step 1: Run the full targeted suite**

Run:

```bash
python -m unittest tests.test_workflow_metadata tests.test_comfyapp_auto_warmup tests.test_modal_client_gpu_config tests.test_modal_runtime_routes tests.test_restore_timing_data_flow -v
```

Expected: PASS with the new activation, restore-selection, and logging tests included.

- [ ] **Step 2: Run a source-level grep sanity check for stale selector usage**

Run:

```bash
python -c "from pathlib import Path; src = Path('comfyapp.py').read_text(encoding='utf-8'); needle = 'source = \"last_stack\"'; assert needle not in src, f'found forbidden stale selector: {needle}'; print('ok: no last_stack restore selector remains')"
```

Expected: `ok: no last_stack restore selector remains`

- [ ] **Step 3: Commit**

```bash
git add workflow_metadata.py comfyapp.py modal_client.py __init__.py tests/test_workflow_metadata.py tests/test_comfyapp_auto_warmup.py tests/test_modal_client_gpu_config.py tests/test_modal_runtime_routes.py tests/test_restore_timing_data_flow.py
git commit -m "test: cover active warmup profile selection flow"
```

## Spec coverage check

- Active-next profile first, env default second, no warmup third: covered by Tasks 2 and 4.
- `last_stack` no longer acts as restore-time authority: covered by Tasks 2 and 4.
- CPU-only setter that does not initialize the main runner: covered by Task 2.
- TTL + token + explicit disable-warmup behavior: covered by Tasks 2 and 3.
- Prompt-time mismatch logging with `WARMUP_PROFILE_MATCH`: covered by Task 4.
- No phase-1 registry: preserved by all tasks; no registry file is introduced.

## Placeholder scan

- No `TODO`, `TBD`, or “implement later” steps remain in the task list.
- Every code-edit step includes concrete code blocks.
- Every verification step includes an exact command and expected result.

## Type consistency check

- Shared helper names are consistent across plan steps: `extract_warmup_stack`, `stack_to_warmup_profile`, `warmup_profile_matches_stack`, `set_active_warmup_profile`, `_build_next_warmup_activation`.
- The active-next payload shape is consistent across storage, client wrapper, local dispatch, and restore logs.
