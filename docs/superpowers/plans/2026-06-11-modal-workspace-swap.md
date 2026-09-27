# Modal Workspace Swap Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let one local ComfyUI install save and swap among multiple Modal workspaces, reconcile manifest-backed models into the selected workspace, sync custom nodes, and expose manifest repair plus workflow manifest export/import from the existing sidebar.

**Architecture:** Keep persistence local to the custom node with two JSON-backed helpers: one for workspace registry/state and one for model manifest state. Replace `modal_client.py`'s import-time global handles with explicit per-workspace `modal.Client.from_credentials` handle factories, then route all backend Modal actions through the selected workspace or an explicit swap target. Use one background swap job with polled progress so the sidebar can show phase labels while the backend performs repair checks, downloads missing models, syncs custom nodes, and starts a workspace-scoped deploy.

**Tech Stack:** Python 3.11, Modal Python SDK, aiohttp route handlers, vanilla JavaScript sidebar UI, built-in `unittest`, filesystem-backed JSON state.

---

## File map

- Create: `modal_workspaces.py` — local workspace registry persistence, validation, active-selection helpers, masked summaries, and per-workspace deploy-state storage.
- Create: `model_manifest.py` — master manifest persistence, repair scanning, install-entry upserts, swap planning, workflow export, and workflow import merge/conflict handling.
- Modify: `modal_client.py` — remove import-time single-workspace handles, add explicit per-workspace clients/handles, and preserve existing function names with optional `workspace=` overrides.
- Modify: `workflow_metadata.py` — add workflow model-reference extraction that covers the repo's current loader set plus `DualCLIPLoader`.
- Modify: `__init__.py` — wire workspace resolver setup, per-workspace deploy env, manifest writes on installs, swap orchestration, new route families, and sidebar-facing responses.
- Modify: `web/modal-settings.js` — replace single-token auth UX with workspace management, swap progress, manifest repair modal, and workflow manifest export/import controls.
- Create: `tests/test_modal_workspaces.py` — workspace registry persistence/unit tests.
- Create: `tests/test_modal_client_workspaces.py` — explicit-client Modal handle tests.
- Create: `tests/test_model_manifest.py` — manifest repair/export/import/swap planning tests.
- Modify: `tests/test_workflow_metadata.py` — add workflow model-reference extraction tests.
- Create: `tests/test_modal_workspace_backend.py` — backend helper/route tests with stubbed `PromptServer` and `modal_client` modules.
- Create: `tests/test_modal_workspace_ui_ast.py` — AST/text tests that the new sidebar controls and route calls exist.

## Notes before coding

- Do **not** add git commit steps during execution unless the user explicitly asks.
- Do **not** keep writing `~/.modal.toml` as the active source of truth for workspaces. The SDK path must use explicit `modal.Client.from_credentials`, and `modal deploy` must receive `MODAL_TOKEN_ID` / `MODAL_TOKEN_SECRET` through the subprocess environment.
- Keep state files inside the custom node directory:
  - `._modal_workspaces.json`
  - `.model_manifest.json`
- Reuse the existing `.deployed_state.json` only as a one-time legacy source when a workspace does not yet have deploy-state metadata; after migration, persist deploy state per workspace inside the workspace registry file.
- Keep current public route prefixes under `/comfymodal/*`; add new route families instead of inventing a second prefix.
- Preserve current placeholder behavior. This plan only adds manifest bookkeeping and workspace-aware routing around existing downloads/sync flows.

### Task 1: Add workspace registry persistence

**Files:**
- Create: `modal_workspaces.py`
- Create: `tests/test_modal_workspaces.py`

- [ ] **Step 1: Write the failing workspace-registry tests**

Create `tests/test_modal_workspaces.py` with this content:

```python
import importlib.util
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = REPO_ROOT / "modal_workspaces.py"


def load_module():
    if not MODULE_PATH.exists():
        raise AssertionError("modal_workspaces.py missing")
    spec = importlib.util.spec_from_file_location("modal_workspaces", MODULE_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ModalWorkspaceRegistryTests(unittest.TestCase):
    def test_save_and_reload_preserves_active_workspace(self):
        module = load_module()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / ".modal_workspaces.json"
            saved = module.upsert_workspace(
                path,
                label="Studio A",
                token_id="ak-studio-a",
                token_secret="as-studio-a",
                set_active=True,
            )
            loaded = module.load_workspace_registry(path)

        self.assertEqual(saved["active_workspace_id"], loaded["active_workspace_id"])
        self.assertEqual(len(loaded["workspaces"]), 1)
        self.assertEqual(loaded["workspaces"][0]["label"], "Studio A")

    def test_workspace_summary_masks_secret(self):
        module = load_module()
        summary = module.workspace_summary({
            "id": "ws_1",
            "label": "Studio A",
            "token_id": "ak-1234567890",
            "token_secret": "as-abcdefghijklmnopqrstuvwxyz",
            "last_used_at": None,
            "last_deploy_status": "idle",
            "notes": "",
        })

        self.assertEqual(summary["token_id_masked"], "ak-1234…7890")
        self.assertTrue(summary["token_secret_masked"].startswith("as-"))
        self.assertNotIn("token_secret", summary)

    def test_set_active_workspace_updates_last_used(self):
        module = load_module()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / ".modal_workspaces.json"
            first = module.upsert_workspace(path, "Studio A", "ak-a", "as-a", set_active=False)
            second = module.upsert_workspace(path, "Studio B", "ak-b", "as-b", set_active=False)
            second_id = second["workspaces"][1]["id"]

            updated = module.set_active_workspace(path, second_id)
            active = module.get_active_workspace(updated)

        self.assertEqual(active["label"], "Studio B")
        self.assertEqual(updated["active_workspace_id"], second_id)
        self.assertIsNotNone(active["last_used_at"])

    def test_invalid_token_prefix_is_rejected(self):
        module = load_module()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / ".modal_workspaces.json"
            with self.assertRaises(ValueError):
                module.upsert_workspace(path, "Bad", "token-id", "secret", set_active=False)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the tests to confirm they fail**

Run: `python -m unittest tests.test_modal_workspaces -v`

Expected: FAIL with `AssertionError: modal_workspaces.py missing`

- [ ] **Step 3: Create `modal_workspaces.py`**

Create `modal_workspaces.py` with this content:

```python
import json
import time
import uuid
from pathlib import Path


def _default_registry() -> dict:
    return {
        "version": 1,
        "active_workspace_id": None,
        "workspaces": [],
        "deploy_state_by_workspace": {},
    }


def load_workspace_registry(path: str | Path) -> dict:
    target = Path(path)
    try:
        payload = json.loads(target.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return _default_registry()
    except json.JSONDecodeError:
        return _default_registry()
    if not isinstance(payload, dict):
        return _default_registry()
    merged = _default_registry()
    merged.update({k: payload.get(k, merged[k]) for k in merged})
    if not isinstance(merged["workspaces"], list):
        merged["workspaces"] = []
    if not isinstance(merged["deploy_state_by_workspace"], dict):
        merged["deploy_state_by_workspace"] = {}
    return merged


def save_workspace_registry(path: str | Path, payload: dict) -> dict:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(target.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    tmp.replace(target)
    return payload


def _validate_workspace(label: str, token_id: str, token_secret: str) -> tuple[str, str, str]:
    safe_label = (label or "").strip()
    safe_token_id = (token_id or "").strip()
    safe_token_secret = (token_secret or "").strip()
    if not safe_label:
        raise ValueError("label required")
    if not safe_token_id.startswith("ak-"):
        raise ValueError("token_id must start with ak-")
    if not safe_token_secret.startswith("as-"):
        raise ValueError("token_secret must start with as-")
    return safe_label, safe_token_id, safe_token_secret


def _mask_token(token: str) -> str:
    if not token:
        return ""
    if len(token) <= 10:
        return token[:4] + "…"
    return f"{token[:7]}…{token[-4:]}"


def workspace_summary(workspace: dict) -> dict:
    return {
        "id": workspace["id"],
        "label": workspace["label"],
        "token_id_masked": _mask_token(workspace.get("token_id", "")),
        "token_secret_masked": _mask_token(workspace.get("token_secret", "")),
        "last_used_at": workspace.get("last_used_at"),
        "last_deploy_status": workspace.get("last_deploy_status", "idle"),
        "notes": workspace.get("notes", ""),
    }


def upsert_workspace(path: str | Path, label: str, token_id: str, token_secret: str, *,
                     workspace_id: str | None = None, notes: str = "", set_active: bool = False) -> dict:
    safe_label, safe_token_id, safe_token_secret = _validate_workspace(label, token_id, token_secret)
    registry = load_workspace_registry(path)
    workspaces = []
    matched_id = workspace_id
    for existing in registry["workspaces"]:
        if workspace_id and existing["id"] == workspace_id:
            matched_id = existing["id"]
            workspaces.append({
                **existing,
                "label": safe_label,
                "token_id": safe_token_id,
                "token_secret": safe_token_secret,
                "notes": notes,
            })
        else:
            workspaces.append(existing)
    if matched_id is None:
        matched_id = f"ws_{uuid.uuid4().hex[:12]}"
        workspaces.append({
            "id": matched_id,
            "label": safe_label,
            "token_id": safe_token_id,
            "token_secret": safe_token_secret,
            "last_used_at": None,
            "last_deploy_status": "idle",
            "notes": notes,
        })
    registry["workspaces"] = workspaces
    if set_active or registry["active_workspace_id"] is None:
        registry["active_workspace_id"] = matched_id
        for workspace in registry["workspaces"]:
            if workspace["id"] == matched_id:
                workspace["last_used_at"] = time.time()
    return save_workspace_registry(path, registry)


def set_active_workspace(path: str | Path, workspace_id: str) -> dict:
    registry = load_workspace_registry(path)
    for workspace in registry["workspaces"]:
        if workspace["id"] == workspace_id:
            workspace["last_used_at"] = time.time()
            registry["active_workspace_id"] = workspace_id
            return save_workspace_registry(path, registry)
    raise KeyError(f"unknown workspace: {workspace_id}")


def get_active_workspace(registry: dict) -> dict | None:
    active_id = registry.get("active_workspace_id")
    for workspace in registry.get("workspaces", []):
        if workspace.get("id") == active_id:
            return workspace
    return None


def get_workspace(registry: dict, workspace_id: str) -> dict | None:
    for workspace in registry.get("workspaces", []):
        if workspace.get("id") == workspace_id:
            return workspace
    return None
```

- [ ] **Step 4: Run the registry tests again**

Run: `python -m unittest tests.test_modal_workspaces -v`

Expected: PASS

### Task 2: Make `modal_client.py` workspace-aware

**Files:**
- Modify: `modal_client.py:1-294`
- Create: `tests/test_modal_client_workspaces.py`

- [ ] **Step 1: Add failing Modal-client workspace tests**

Create `tests/test_modal_client_workspaces.py` with this content:

```python
import asyncio
import importlib.util
import sys
import types
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = REPO_ROOT / "modal_client.py"


class _FakeRemoteCallable:
    def __init__(self, label, calls):
        self.label = label
        self.calls = calls

    def remote(self, *args, **kwargs):
        self.calls.append((self.label, args, kwargs))
        return {"label": self.label, "args": args, "kwargs": kwargs}


def load_module(fake_modal):
    original_modal = sys.modules.get("modal")
    sys.modules["modal"] = fake_modal
    try:
        spec = importlib.util.spec_from_file_location("modal_client", MODULE_PATH)
        assert spec is not None
        assert spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    finally:
        if original_modal is not None:
            sys.modules["modal"] = original_modal
        else:
            sys.modules.pop("modal", None)


class ModalClientWorkspaceTests(unittest.TestCase):
    def test_list_models_uses_explicit_workspace_client(self):
        calls = []
        fake_modal = types.SimpleNamespace()
        fake_modal.Client = types.SimpleNamespace(
            from_credentials=lambda token_id, token_secret: {"token_id": token_id, "token_secret": token_secret},
        )
        fake_modal.Function = types.SimpleNamespace(
            from_name=lambda app_name, name, client=None: _FakeRemoteCallable(f"{name}:{client['token_id']}", calls),
        )
        fake_modal.Cls = types.SimpleNamespace(from_name=lambda *args, **kwargs: lambda: None)

        module = load_module(fake_modal)
        workspace = {"id": "ws_a", "token_id": "ak-a", "token_secret": "as-a"}
        result = asyncio.run(module.list_models(workspace=workspace))

        self.assertEqual(result["label"], "list_models_cpu:ak-a")
        self.assertEqual(calls[0][0], "list_models_cpu:ak-a")

    def test_workspace_resolver_is_used_when_workspace_kwarg_missing(self):
        calls = []
        fake_modal = types.SimpleNamespace()
        fake_modal.Client = types.SimpleNamespace(
            from_credentials=lambda token_id, token_secret: {"token_id": token_id, "token_secret": token_secret},
        )
        fake_modal.Function = types.SimpleNamespace(
            from_name=lambda app_name, name, client=None: _FakeRemoteCallable(f"{name}:{client['token_id']}", calls),
        )
        fake_modal.Cls = types.SimpleNamespace(from_name=lambda *args, **kwargs: lambda: None)

        module = load_module(fake_modal)
        module.set_workspace_resolver(lambda: {"id": "ws_b", "token_id": "ak-b", "token_secret": "as-b"})
        result = asyncio.run(module.health_check())

        self.assertEqual(result["label"], "health_cpu:ak-b")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the tests to confirm they fail**

Run: `python -m unittest tests.test_modal_client_workspaces -v`

Expected: FAIL because `modal_client.py` still builds import-time singleton handles and does not expose `set_workspace_resolver` or `workspace=` parameters.

- [ ] **Step 3: Refactor `modal_client.py` to explicit per-workspace clients**

Update the top of `modal_client.py` so the import-time handle declarations are replaced with this structure:

```python
import asyncio
import functools
import os
from collections.abc import Callable

import modal

from gpu_catalog import (
    DEFAULT_GPU,
    GPU_CATALOG,
    GPU_BY_VALUE,
    get_available_gpu_options,
    get_default_gpu,
    is_gpu_hidden,
    normalize_gpu_value,
)

APP_NAME = os.environ.get("COMFYMODAL_APP_NAME", "comfyui").strip() or "comfyui"

_run_prompt_semaphore = asyncio.Semaphore(1)
_current_gpu = DEFAULT_GPU
_workspace_resolver: Callable[[], dict | None] | None = None
_workspace_clients: dict[str, object] = {}
_workspace_function_handles: dict[tuple[str, str], object] = {}
_workspace_cls_instances: dict[tuple[str, str], object] = {}
_handle_cache_hits = 0
_handle_cache_misses = 0
```

Add these helpers above `_modal_error_handler`:

```python
def set_workspace_resolver(resolver: Callable[[], dict | None] | None):
    global _workspace_resolver
    _workspace_resolver = resolver


def _resolve_workspace(workspace: dict | None) -> dict:
    candidate = workspace or (_workspace_resolver() if _workspace_resolver else None)
    if not candidate:
        raise RuntimeError("No active Modal workspace selected")
    if not candidate.get("token_id") or not candidate.get("token_secret"):
        raise RuntimeError("Active Modal workspace is missing credentials")
    return candidate


def _workspace_client(workspace: dict):
    key = workspace["id"]
    client = _workspace_clients.get(key)
    if client is None:
        client = modal.Client.from_credentials(workspace["token_id"], workspace["token_secret"])
        _workspace_clients[key] = client
    return client


def _workspace_function(name: str, workspace: dict):
    global _handle_cache_hits, _handle_cache_misses
    key = (workspace["id"], name)
    handle = _workspace_function_handles.get(key)
    if handle is None:
        _handle_cache_misses += 1
        handle = modal.Function.from_name(APP_NAME, name, client=_workspace_client(workspace))
        _workspace_function_handles[key] = handle
    else:
        _handle_cache_hits += 1
    return handle


def _workspace_api(workspace: dict, gpu: str | None = None):
    global _handle_cache_hits, _handle_cache_misses
    selected_gpu = _current_gpu if gpu is None else normalize_gpu_value(gpu)
    entry = GPU_BY_VALUE.get(selected_gpu)
    if entry is None:
        raise ValueError(f"Unsupported GPU: {selected_gpu}")
    key = (workspace["id"], selected_gpu)
    instance = _workspace_cls_instances.get(key)
    if instance is None:
        _handle_cache_misses += 1
        cls_handle = modal.Cls.from_name(APP_NAME, entry["class_name"], client=_workspace_client(workspace))
        instance = cls_handle()
        _workspace_cls_instances[key] = instance
    else:
        _handle_cache_hits += 1
    return instance
```

Update `clear_cache()` to clear all three workspace caches:

```python
def clear_cache():
    global _handle_cache_hits, _handle_cache_misses
    _workspace_clients.clear()
    _workspace_function_handles.clear()
    _workspace_cls_instances.clear()
    _handle_cache_hits = 0
    _handle_cache_misses = 0
```

Then update the public async functions so each accepts `workspace: dict | None = None` and resolves the workspace before calling Modal. For example:

```python
@_modal_error_handler
async def list_models(workspace: dict | None = None) -> dict:
    selected = _resolve_workspace(workspace)
    return await asyncio.to_thread(lambda: _workspace_function("list_models_cpu", selected).remote())


@_modal_error_handler
async def health_check(workspace: dict | None = None) -> dict:
    selected = _resolve_workspace(workspace)
    return await asyncio.to_thread(lambda: _workspace_function("health_cpu", selected).remote())


@_modal_error_handler
async def get_object_info(workspace: dict | None = None) -> dict:
    selected = _resolve_workspace(workspace)
    return await asyncio.to_thread(lambda: _workspace_api(selected).object_info.remote())


@_modal_error_handler
async def batch_download_models(items: list, hf_token: str = "", civitai_token: str = "", workspace: dict | None = None) -> list:
    selected = _resolve_workspace(workspace)
    kwargs = {"hf_token": hf_token}
    if civitai_token:
        kwargs["civitai_token"] = civitai_token
    return await asyncio.to_thread(lambda: _workspace_function("batch_download_models", selected).remote(items, **kwargs))
```

Use the same `selected = _resolve_workspace(workspace)` pattern for:

- `run_prompt`
- `run_prompt_stream`
- `health_check`
- `download_model`
- `download_model_stream`
- `delete_model`
- `sync_custom_nodes`
- `refresh_custom_nodes`
- `get_sync_status`
- `upload_model_to_volume`
- `upload_model_chunk`
- `resync_runtime`
- `get_runtime_state`
- `set_active_warmup_profile`

- [ ] **Step 4: Run the Modal-client workspace tests again**

Run: `python -m unittest tests.test_modal_client_workspaces -v`

Expected: PASS

### Task 3: Add master-manifest and workflow-manifest helpers

**Files:**
- Create: `model_manifest.py`
- Create: `tests/test_model_manifest.py`
- Modify: `workflow_metadata.py:1-175`
- Modify: `tests/test_workflow_metadata.py:1-103`

- [ ] **Step 1: Write the failing manifest tests**

Create `tests/test_model_manifest.py` with this content:

```python
import importlib.util
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = REPO_ROOT / "model_manifest.py"


def load_module():
    if not MODULE_PATH.exists():
        raise AssertionError("model_manifest.py missing")
    spec = importlib.util.spec_from_file_location("model_manifest", MODULE_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ModelManifestTests(unittest.TestCase):
    def test_upsert_manifest_entry_persists_folder_filename_and_url(self):
        module = load_module()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / ".model_manifest.json"
            saved = module.upsert_manifest_entry(path, {
                "folder": "vae",
                "filename": "flux2-vae.safetensors",
                "url": "https://huggingface.co/acme/flux2-vae/resolve/main/flux2-vae.safetensors",
                "source_kind": "huggingface",
                "requires_hf_token": False,
                "requires_civitai_token": False,
            })

        self.assertEqual(saved["entries"][0]["folder"], "vae")
        self.assertEqual(saved["entries"][0]["filename"], "flux2-vae.safetensors")

    def test_scan_manifest_issues_flags_missing_url_duplicate_and_invalid_folder(self):
        module = load_module()
        payload = {
            "manifest_version": 1,
            "entries": [
                {"folder": "vae", "filename": "a.safetensors", "url": "", "source_kind": "huggingface"},
                {"folder": "vae", "filename": "b.safetensors", "url": "https://x", "source_kind": ""},
                {"folder": "bad-folder", "filename": "c.safetensors", "url": "https://x", "source_kind": "direct"},
                {"folder": "vae", "filename": "dup.safetensors", "url": "https://one", "source_kind": "direct"},
                {"folder": "vae", "filename": "dup.safetensors", "url": "https://two", "source_kind": "direct"},
            ],
        }
        issues = module.scan_manifest_issues(payload)
        issue_kinds = {item["kind"] for item in issues}

        self.assertEqual(issue_kinds, {"missing_url", "missing_source_kind", "invalid_folder", "duplicate_key"})

    def test_build_swap_plan_separates_present_missing_and_unresolved(self):
        module = load_module()
        manifest = {
            "manifest_version": 1,
            "entries": [
                {"folder": "vae", "filename": "flux2-vae.safetensors", "url": "https://example/vae", "source_kind": "direct"},
                {"folder": "loras", "filename": "detail.safetensors", "url": "", "source_kind": "direct"},
            ],
        }
        remote_models = [{"folder": "vae", "name": "flux2-vae.safetensors"}]
        plan = module.build_workspace_swap_plan(manifest, remote_models)

        self.assertEqual(plan["already_present"], [{"folder": "vae", "filename": "flux2-vae.safetensors"}])
        self.assertEqual(plan["to_install"], [])
        self.assertEqual(plan["unresolved"][0]["filename"], "detail.safetensors")

    def test_merge_workflow_manifest_returns_conflicts_instead_of_overwriting(self):
        module = load_module()
        local_payload = {
            "manifest_version": 1,
            "entries": [
                {"folder": "vae", "filename": "flux2-vae.safetensors", "url": "https://local", "source_kind": "direct"},
            ],
        }
        imported_payload = {
            "manifest_version": 1,
            "models": [
                {"folder": "vae", "filename": "flux2-vae.safetensors", "url": "https://remote", "source_kind": "direct"},
            ],
        }
        result = module.merge_workflow_manifest(local_payload, imported_payload)

        self.assertEqual(result["added"], [])
        self.assertEqual(len(result["conflicts"]), 1)
        self.assertEqual(result["conflicts"][0]["filename"], "flux2-vae.safetensors")

    def test_apply_manifest_repairs_updates_missing_url(self):
        module = load_module()
        payload = {
            "manifest_version": 1,
            "entries": [
                {"folder": "vae", "filename": "flux2-vae.safetensors", "url": "", "source_kind": ""},
            ],
        }
        repaired = module.apply_manifest_repairs(payload, [{
            "folder": "vae",
            "filename": "flux2-vae.safetensors",
            "url": "https://example/flux2-vae.safetensors",
            "source_kind": "direct",
        }])

        self.assertEqual(repaired["entries"][0]["url"], "https://example/flux2-vae.safetensors")
        self.assertEqual(repaired["entries"][0]["source_kind"], "direct")

    def test_merge_workflow_manifest_applies_explicit_resolution(self):
        module = load_module()
        local_payload = {
            "manifest_version": 1,
            "entries": [
                {"folder": "vae", "filename": "flux2-vae.safetensors", "url": "https://local", "source_kind": "direct"},
            ],
        }
        imported_payload = {
            "manifest_version": 1,
            "models": [
                {"folder": "vae", "filename": "flux2-vae.safetensors", "url": "https://remote", "source_kind": "direct"},
            ],
        }
        result = module.merge_workflow_manifest(
            local_payload,
            imported_payload,
            resolutions={"vae/flux2-vae.safetensors": "use_imported"},
        )

        self.assertEqual(result["conflicts"], [])
        self.assertEqual(result["entries"][0]["url"], "https://remote")


if __name__ == "__main__":
    unittest.main()
```

Append these tests to `tests/test_workflow_metadata.py`:

```python
    def test_extract_model_refs_includes_dual_clip_entries(self):
        refs = extract_workflow_model_refs(WORKFLOW_DUAL_CLIP_FLUX)
        filenames = {(item["role"], item["filename"]) for item in refs}
        self.assertIn(("clip", "t5xxl_fp16.safetensors"), filenames)
        self.assertIn(("clip", "clip_l.safetensors"), filenames)

    def test_extract_model_refs_deduplicates_same_loader_value(self):
        refs = extract_workflow_model_refs({
            "1": {"class_type": "CLIPLoader", "inputs": {"clip_name": "clip_l.safetensors"}},
            "2": {"class_type": "CLIPLoader", "inputs": {"clip_name": "clip_l.safetensors"}},
        })
        self.assertEqual(refs, [{"role": "clip", "filename": "clip_l.safetensors"}])
```

- [ ] **Step 2: Run the manifest tests to confirm they fail**

Run: `python -m unittest tests.test_model_manifest tests.test_workflow_metadata -v`

Expected: FAIL because `model_manifest.py` and `extract_workflow_model_refs` do not exist yet.

- [ ] **Step 3: Create `model_manifest.py` and extend `workflow_metadata.py`**

Create `model_manifest.py` with this content:

```python
import json
import time
from pathlib import Path

from local_placeholders import ALLOWED_MODEL_FOLDERS, normalize_model_filename, normalize_model_folder
from workflow_metadata import extract_workflow_model_refs


WORKFLOW_ROLE_FOLDERS = {
    "checkpoint": {"checkpoints"},
    "unet": {"unet", "diffusion_models"},
    "clip": {"clip", "text_encoders"},
    "vae": {"vae"},
    "lora": {"loras"},
    "controlnet": {"controlnet"},
}


def _default_manifest() -> dict:
    return {"manifest_version": 1, "entries": []}


def load_master_manifest(path: str | Path) -> dict:
    target = Path(path)
    try:
        payload = json.loads(target.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return _default_manifest()
    if not isinstance(payload, dict) or not isinstance(payload.get("entries"), list):
        return _default_manifest()
    return payload


def save_master_manifest(path: str | Path, payload: dict) -> dict:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(target.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    tmp.replace(target)
    return payload


def infer_source_kind(url: str) -> str:
    lower = (url or "").lower()
    if "huggingface.co" in lower:
        return "huggingface"
    if "civitai.com" in lower:
        return "civitai"
    if lower.startswith("http://") or lower.startswith("https://"):
        return "direct"
    return "unknown"


def normalize_manifest_entry(entry: dict, now: float | None = None) -> dict:
    now_value = time.time() if now is None else now
    folder = normalize_model_folder(entry.get("folder", ""))
    filename = normalize_model_filename(entry.get("filename", ""))
    url = (entry.get("url") or "").strip()
    source_kind = (entry.get("source_kind") or infer_source_kind(url)).strip() or "unknown"
    return {
        "folder": folder,
        "filename": filename,
        "url": url,
        "source_kind": source_kind,
        "requires_hf_token": bool(entry.get("requires_hf_token", False)),
        "requires_civitai_token": bool(entry.get("requires_civitai_token", False)),
        "sha256": entry.get("sha256") or None,
        "notes": entry.get("notes") or "",
        "added_at": entry.get("added_at") or now_value,
        "updated_at": now_value,
    }


def upsert_manifest_entry(path: str | Path, entry: dict) -> dict:
    payload = load_master_manifest(path)
    normalized = normalize_manifest_entry(entry)
    replaced = False
    entries = []
    for existing in payload["entries"]:
        if (existing.get("folder"), existing.get("filename")) == (normalized["folder"], normalized["filename"]):
            entries.append({**existing, **normalized, "added_at": existing.get("added_at") or normalized["added_at"]})
            replaced = True
        else:
            entries.append(existing)
    if not replaced:
        entries.append(normalized)
    payload["entries"] = sorted(entries, key=lambda item: (item["folder"], item["filename"]))
    return save_master_manifest(path, payload)


def scan_manifest_issues(payload: dict) -> list[dict]:
    issues = []
    seen = {}
    for entry in payload.get("entries", []):
        key = (entry.get("folder"), entry.get("filename"))
        seen.setdefault(key, []).append(entry)
        if not entry.get("url"):
            issues.append({"kind": "missing_url", **entry})
        if not entry.get("source_kind"):
            issues.append({"kind": "missing_source_kind", **entry})
        if entry.get("folder") not in ALLOWED_MODEL_FOLDERS:
            issues.append({"kind": "invalid_folder", **entry})
    for key, entries in seen.items():
        if len(entries) > 1:
            issues.append({"kind": "duplicate_key", "folder": key[0], "filename": key[1], "count": len(entries)})
    return issues


def build_workspace_swap_plan(payload: dict, remote_models: list[dict]) -> dict:
    remote_keys = {(item.get("folder"), item.get("name")) for item in remote_models}
    already_present = []
    to_install = []
    unresolved = []
    for entry in payload.get("entries", []):
        key = (entry.get("folder"), entry.get("filename"))
        if key in remote_keys:
            already_present.append({"folder": key[0], "filename": key[1]})
        elif not entry.get("url"):
            unresolved.append({"folder": key[0], "filename": key[1], "reason": "missing_url"})
        else:
            to_install.append({
                "url": entry["url"],
                "filename": entry["filename"],
                "save_path": entry["folder"],
                "requires_hf_token": bool(entry.get("requires_hf_token")),
                "requires_civitai_token": bool(entry.get("requires_civitai_token")),
            })
    return {"already_present": already_present, "to_install": to_install, "unresolved": unresolved}


def apply_manifest_repairs(payload: dict, updates: list[dict]) -> dict:
    indexed = {(item.get("folder"), item.get("filename")): dict(item) for item in payload.get("entries", [])}
    for update in updates:
        key = (update.get("folder"), update.get("filename"))
        if key not in indexed:
            continue
        current = indexed[key]
        if update.get("skip"):
            current.setdefault("notes", "")
            current["notes"] = (current["notes"] + "\nrepair skipped").strip()
            current["updated_at"] = time.time()
            continue
        merged = {**current, **update}
        indexed[key] = normalize_manifest_entry(merged, now=time.time())
    return {"manifest_version": payload.get("manifest_version", 1), "entries": list(indexed.values())}


def export_workflow_manifest(master_manifest: dict, prompt: dict, workflow_name: str = "") -> dict:
    by_filename = {}
    for entry in master_manifest.get("entries", []):
        by_filename.setdefault(entry.get("filename"), []).append(entry)
    models = []
    unresolved = []
    for ref in extract_workflow_model_refs(prompt):
        allowed = WORKFLOW_ROLE_FOLDERS.get(ref["role"], set())
        matches = [item for item in by_filename.get(ref["filename"], []) if item.get("folder") in allowed]
        if len(matches) != 1 or not matches[0].get("url"):
            unresolved.append(ref)
            continue
        match = matches[0]
        models.append({
            "folder": match["folder"],
            "filename": match["filename"],
            "url": match["url"],
            "source_kind": match["source_kind"],
            "requires_hf_token": bool(match.get("requires_hf_token")),
            "requires_civitai_token": bool(match.get("requires_civitai_token")),
            "notes": match.get("notes") or "",
        })
    return {
        "manifest_version": 1,
        "exported_at": time.time(),
        "workflow_name": workflow_name,
        "models": models,
        "unresolved": unresolved,
    }


def merge_workflow_manifest(local_payload: dict, imported_payload: dict, resolutions: dict[str, str] | None = None) -> dict:
    local_entries = list(local_payload.get("entries", []))
    by_key = {(item.get("folder"), item.get("filename")): item for item in local_entries}
    added = []
    filled = []
    conflicts = []
    resolutions = resolutions or {}
    for imported in imported_payload.get("models", []):
        key = (imported.get("folder"), imported.get("filename"))
        existing = by_key.get(key)
        if existing is None:
            local_entries.append(normalize_manifest_entry(imported))
            by_key[key] = local_entries[-1]
            added.append({"folder": key[0], "filename": key[1]})
            continue
        if not existing.get("url") and imported.get("url"):
            existing.update(normalize_manifest_entry({**existing, **imported, "added_at": existing.get("added_at")}))
            filled.append({"folder": key[0], "filename": key[1]})
            continue
        if existing.get("url") and imported.get("url") and existing.get("url") != imported.get("url"):
            resolution = resolutions.get(f"{key[0]}/{key[1]}")
            if resolution == "use_imported":
                existing.update(normalize_manifest_entry({**existing, **imported, "added_at": existing.get("added_at")}))
                continue
            if resolution == "keep_local" or resolution == "skip":
                continue
            conflicts.append({
                "folder": key[0],
                "filename": key[1],
                "local_url": existing.get("url"),
                "imported_url": imported.get("url"),
            })
    return {"entries": local_entries, "added": added, "filled": filled, "conflicts": conflicts}
```

Update `workflow_metadata.py` by adding this mapping and helper below `extract_model_stack`:

```python
_MODEL_REF_MAPPINGS: dict[str, list[tuple[str, str]]] = {
    "CheckpointLoaderSimple": [("checkpoint", "ckpt_name")],
    "CheckpointLoader": [("checkpoint", "ckpt_name")],
    "UNETLoader": [("unet", "unet_name")],
    "CLIPLoader": [("clip", "clip_name")],
    "DualCLIPLoader": [("clip", "clip_name1"), ("clip", "clip_name2")],
    "VAELoader": [("vae", "vae_name")],
    "LoraLoader": [("lora", "lora_name")],
    "LoraLoaderModelOnly": [("lora", "lora_name")],
    "ControlNetLoader": [("controlnet", "control_net_name")],
}


def extract_workflow_model_refs(prompt: dict) -> list[dict[str, str]]:
    seen = set()
    refs = []
    for node in prompt.values():
        if not isinstance(node, dict):
            continue
        inputs = node.get("inputs", {})
        mappings = _MODEL_REF_MAPPINGS.get(node.get("class_type", ""), [])
        for role, field in mappings:
            value = inputs.get(field)
            if not isinstance(value, str) or not value:
                continue
            key = (role, value)
            if key in seen:
                continue
            seen.add(key)
            refs.append({"role": role, "filename": value})
    return refs
```

Also update the import list at the top of `tests/test_workflow_metadata.py` so it includes `extract_workflow_model_refs`.

- [ ] **Step 4: Run the manifest tests again**

Run: `python -m unittest tests.test_model_manifest tests.test_workflow_metadata -v`

Expected: PASS

### Task 4: Wire backend workspace, manifest, and swap routes

**Files:**
- Modify: `__init__.py:103-399`, `__init__.py:547-695`, `__init__.py:1646-2552`
- Create: `tests/test_modal_workspace_backend.py`

- [ ] **Step 1: Add failing backend tests**

Create `tests/test_modal_workspace_backend.py` with this content:

```python
import asyncio
import importlib.util
import json
import sys
import tempfile
import types
import unittest
import uuid
from pathlib import Path
from unittest.mock import MagicMock, patch


REPO_ROOT = Path(__file__).resolve().parents[1]
INIT_PATH = REPO_ROOT / "__init__.py"


class _Routes:
    def __init__(self):
        self.handlers = {}

    def _register(self, method, path):
        def decorator(fn):
            self.handlers[(method, path)] = fn
            return fn
        return decorator

    def get(self, path):
        return self._register("GET", path)

    def post(self, path):
        return self._register("POST", path)

    def delete(self, path):
        return self._register("DELETE", path)


def _make_modal_stub():
    stub = types.ModuleType("modal")
    stub.Image = MagicMock()
    stub.Image.debian_slim.return_value.apt_install.return_value.pip_install.return_value.run_commands.return_value = MagicMock()
    stub.App = MagicMock()
    stub.App.return_value.function = lambda **kw: (lambda f: f)
    stub.App.return_value.cls = lambda **kw: (lambda c: c)
    stub.Volume = MagicMock()
    stub.Volume.from_name.return_value = MagicMock()
    stub.Secret = MagicMock()
    stub.Secret.from_name.return_value = MagicMock()
    stub.Client = types.SimpleNamespace(from_credentials=lambda token_id, token_secret: {"token_id": token_id, "token_secret": token_secret})
    stub.Function = types.SimpleNamespace(from_name=lambda *args, **kwargs: MagicMock())
    stub.Cls = types.SimpleNamespace(from_name=lambda *args, **kwargs: (lambda: MagicMock()))
    stub.web_server = lambda *a, **kw: (lambda f: f)
    stub.enter = lambda **kw: (lambda f: f)
    stub.exit = lambda: (lambda f: f)
    stub.method = lambda *a, **kw: (lambda f: f)
    stub.concurrent = lambda **kw: (lambda c: c)
    return stub


def _make_modal_client_stub():
    stub = types.ModuleType("modal_client")

    async def _async_ok(*args, **kwargs):
        return {"status": "ok"}

    for name in (
        "run_prompt", "run_prompt_stream", "get_object_info", "health_check",
        "download_model", "download_model_stream", "batch_download_models", "list_models",
        "delete_model", "sync_custom_nodes", "refresh_custom_nodes", "get_sync_status",
        "upload_model_to_volume", "upload_model_chunk", "resync_runtime", "get_runtime_state",
        "set_active_warmup_profile",
    ):
        setattr(stub, name, _async_ok)

    setattr(stub, "clear_cache", lambda: None)
    setattr(stub, "set_workspace_resolver", lambda resolver: None)
    setattr(stub, "set_gpu", lambda gpu: None)
    setattr(stub, "get_gpu", lambda: "a10g")
    setattr(stub, "get_default_gpu", lambda: "a10g")
    setattr(stub, "get_available_gpus", lambda: [{"value": "a10g", "label": "A10G"}])
    setattr(stub, "get_handle_cache_stats", lambda: {"hits": 0, "misses": 0})
    setattr(stub, "get_modal_app_name", lambda: "comfyui")
    setattr(stub, "get_modal_class_name", lambda gpu=None: "ComfyAPI")
    setattr(stub, "get_modal_lookup_target", lambda gpu=None, method_name="run_prompt": f"comfyui.ComfyAPI.{method_name}")
    return stub


def _load_init_module():
    routes = _Routes()
    prompt_server = types.SimpleNamespace(instance=types.SimpleNamespace(routes=routes, send_sync=lambda *a, **kw: None, prompt_queue=None))
    server_module = types.ModuleType("server")
    server_module.PromptServer = prompt_server
    execution_module = types.ModuleType("execution")

    original_modules = {name: sys.modules.get(name) for name in ("modal", "modal_client", "server", "execution")}
    sys.modules["modal"] = _make_modal_stub()
    sys.modules["modal_client"] = _make_modal_client_stub()
    sys.modules["server"] = server_module
    sys.modules["execution"] = execution_module
    module_name = f"modal_init_test_{uuid.uuid4().hex}"
    try:
        spec = importlib.util.spec_from_file_location(module_name, str(INIT_PATH))
        assert spec is not None
        assert spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        with patch("threading.Thread") as thread_cls:
            thread_cls.return_value.start.return_value = None
            spec.loader.exec_module(module)
        return module, routes.handlers
    finally:
        for name, original in original_modules.items():
            if original is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = original
        sys.modules.pop(module_name, None)


class _Request:
    def __init__(self, body=None, match_info=None, query=None):
        self._body = body or {}
        self.match_info = match_info or {}
        self.rel_url = types.SimpleNamespace(query=query or {})
        self.content_length = None

    async def json(self):
        return self._body


class ModalWorkspaceBackendTests(unittest.TestCase):
    def test_routes_are_registered(self):
        _, handlers = _load_init_module()
        self.assertIn(("GET", "/comfymodal/workspaces"), handlers)
        self.assertIn(("POST", "/comfymodal/workspaces/active"), handlers)
        self.assertIn(("POST", "/comfymodal/workspaces/swap"), handlers)
        self.assertIn(("GET", "/comfymodal/manifest"), handlers)
        self.assertIn(("POST", "/comfymodal/manifest/repair/scan"), handlers)
        self.assertIn(("POST", "/comfymodal/manifest/repair/apply"), handlers)
        self.assertIn(("POST", "/comfymodal/workflow-manifest/import"), handlers)

    def test_swap_route_requires_confirmation_when_prompt_running(self):
        module, handlers = _load_init_module()
        handler = handlers[("POST", "/comfymodal/workspaces/swap")]
        with tempfile.TemporaryDirectory() as tmp:
            with (
                patch.object(module, "_WORKSPACES_FILE", str(Path(tmp) / ".modal_workspaces.json")),
                patch.object(module, "_ACTIVE_REQUEST_IDS", {"prompt-1": 1.0}),
            ):
                registry = module._workspace_store().upsert_workspace(module._WORKSPACES_FILE, "Studio A", "ak-a", "as-a", set_active=True)
                workspace_id = registry["workspaces"][0]["id"]
                response = asyncio.run(handler(_Request({"workspace_id": workspace_id})))
                payload = json.loads(response.text)

        self.assertEqual(payload["status"], "confirm_required")

    def test_manifest_repair_scan_returns_issues(self):
        module, handlers = _load_init_module()
        handler = handlers[("POST", "/comfymodal/manifest/repair/scan")]
        with tempfile.TemporaryDirectory() as tmp:
            manifest_path = Path(tmp) / ".model_manifest.json"
            manifest_path.write_text(json.dumps({
                "manifest_version": 1,
                "entries": [{"folder": "vae", "filename": "flux2-vae.safetensors", "url": "", "source_kind": "direct"}],
            }), encoding="utf-8")
            with patch.object(module, "_MODEL_MANIFEST_FILE", str(manifest_path)):
                response = asyncio.run(handler(_Request()))
                payload = json.loads(response.text)

        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["issues"][0]["kind"], "missing_url")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the backend tests to confirm they fail**

Run: `python -m unittest tests.test_modal_workspace_backend -v`

Expected: FAIL because the new route family, workspace-store helpers, and swap confirmation response do not exist yet.

- [ ] **Step 3: Add workspace and manifest imports/constants in `__init__.py`**

Add these imports near the existing `local_placeholders` / `workflow_metadata` imports:

```python
import model_manifest as _model_manifest
import modal_workspaces as _workspace_store
```

Add these constants near `_MODAL_SETTINGS_FILE`:

```python
_WORKSPACES_FILE = os.path.join(_NODE_DIR, ".modal_workspaces.json")
_MODEL_MANIFEST_FILE = os.path.join(_NODE_DIR, ".model_manifest.json")
_SWAP_JOB_POLL_INTERVAL_S = 1.0
_swap_jobs: dict[str, dict] = {}
_swap_jobs_lock = threading.Lock()
```

Add these helpers above `_run_deploy_background`:

```python
def _workspace_registry() -> dict:
    return _workspace_store.load_workspace_registry(_WORKSPACES_FILE)


def _active_workspace() -> dict | None:
    return _workspace_store.get_active_workspace(_workspace_registry())


def _workspace_or_400(workspace_id: str) -> dict:
    workspace = _workspace_store.get_workspace(_workspace_registry(), workspace_id)
    if workspace is None:
        raise KeyError(f"unknown workspace: {workspace_id}")
    return workspace


def _workspace_manifest() -> dict:
    return _model_manifest.load_master_manifest(_MODEL_MANIFEST_FILE)


def _save_workspace_deploy_state(workspace_id: str, version: str | None, fingerprint: str | None) -> None:
    registry = _workspace_registry()
    registry.setdefault("deploy_state_by_workspace", {})[workspace_id] = {
        "comfyapp_version": version,
        "custom_nodes_fingerprint": fingerprint,
    }
    _workspace_store.save_workspace_registry(_WORKSPACES_FILE, registry)


def _load_workspace_deploy_state(workspace_id: str) -> dict:
    registry = _workspace_registry()
    deploy_state = registry.get("deploy_state_by_workspace", {}).get(workspace_id)
    if deploy_state:
        return deploy_state
    return _load_deploy_state()
```

Immediately after the `modal_client` import block succeeds, register the resolver and make sure `set_workspace_resolver` is part of that import list:

```python
    set_workspace_resolver(_active_workspace)
```

- [ ] **Step 4: Make deploy and sync helpers workspace-aware**

Update `_run_deploy_background`, `_start_background_deploy`, `_ensure_modal_deploy_current`, and `_sync_custom_nodes_and_maybe_deploy` so they accept a `workspace` dict and use per-workspace deploy state:

```python
def _run_deploy_background(workspace: dict, custom_nodes_fingerprint: str | None = None):
    global _deploy_status
    modal_cmd = _find_modal_executable()
    if not modal_cmd:
        _deploy_status = {"state": "error", "message": "modal CLI not found. Run: pip install modal"}
        return

    env = {
        **os.environ,
        "MODAL_TOKEN_ID": workspace["token_id"],
        "MODAL_TOKEN_SECRET": workspace["token_secret"],
        "PYTHONIOENCODING": "utf-8",
    }
    _deploy_status = {"state": "deploying", "message": f"Deploying {workspace['label']}…"}
    process = subprocess.Popen(
        [modal_cmd, "deploy", _COMFYAPP_PATH],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
    )
    combined_lines = []
    with open(_DEPLOY_LOG_FILE, "w", encoding="utf-8") as log_f:
        for line in iter(process.stdout.readline, ""):
            log_f.write(line)
            log_f.flush()
            combined_lines.append(line)
    process.wait(timeout=30)
    combined_output = "".join(combined_lines)
    returncode = process.returncode
    if returncode == 0:
        version = _get_comfyapp_version()
        _save_workspace_deploy_state(workspace["id"], version, custom_nodes_fingerprint)
        _deploy_status = {"state": "ready", "message": f"Deployed {workspace['label']} v{version}"}
    else:
        _deploy_status = {"state": "error", "message": combined_output[:2000], "details": combined_output[:2000]}
```

```python
def _start_background_deploy(workspace: dict, custom_nodes_fingerprint: str | None, reason: str) -> dict:
    global _deploy_status
    if _deploy_status.get("state") == "deploying":
        return {"started": False, "reason": "deploy_already_running"}
    thread = threading.Thread(
        target=_run_deploy_background,
        kwargs={"workspace": workspace, "custom_nodes_fingerprint": custom_nodes_fingerprint},
        daemon=True,
    )
    thread.start()
    return {"started": True, "reason": reason}


def _ensure_modal_deploy_current(workspace: dict, custom_nodes_fingerprint: str | None = None) -> dict:
    current_version = _get_comfyapp_version()
    deployed = _load_workspace_deploy_state(workspace["id"])
    deployed_version = deployed.get("comfyapp_version")
    deployed_fingerprint = deployed.get("custom_nodes_fingerprint")
    if current_version != deployed_version:
        return _start_background_deploy(workspace, custom_nodes_fingerprint, "version_changed")
    if custom_nodes_fingerprint != deployed_fingerprint:
        return _start_background_deploy(workspace, custom_nodes_fingerprint, "custom_nodes_changed")
    return {"started": False, "reason": "already_current"}
```

```python
async def _sync_custom_nodes_and_maybe_deploy(cn_root: str, workspace: dict) -> dict:
    fingerprint = _build_custom_node_fingerprint(cn_root)
    archive_data = _build_custom_nodes_archive(cn_root)
    result = await sync_custom_nodes(archive_data, workspace=workspace)
    if result.get("status") != "ok":
        return result
    result["deploy"] = _ensure_modal_deploy_current(workspace, fingerprint)
    try:
        result["refresh"] = await resync_runtime("custom_nodes", workspace=workspace)
    except Exception as e:
        result["refresh_error"] = str(e)
    return result
```

Also update `_is_modal_token_set()` so it returns `bool(_active_workspace())`.

- [ ] **Step 5: Persist manifest entries on install routes**

Add this helper above the batch/single install routes:

```python
def _manifest_entry_from_install(url: str, folder: str, filename: str) -> dict:
    source_kind = _model_manifest.infer_source_kind(url)
    return {
        "folder": folder,
        "filename": filename,
        "url": url,
        "source_kind": source_kind,
        "requires_hf_token": source_kind == "huggingface",
        "requires_civitai_token": source_kind == "civitai",
    }
```

In `modal_batch_model_install`, after placeholder creation, add:

```python
            manifest_payload = None
            for item in normalized_items:
                manifest_payload = _model_manifest.upsert_manifest_entry(
                    _MODEL_MANIFEST_FILE,
                    _manifest_entry_from_install(item["url"], item["save_path"], item["filename"]),
                )
```

and include this in the response:

```python
                "manifest_entries_written": len(normalized_items),
                "manifest_issue_count": len(_model_manifest.scan_manifest_issues(manifest_payload or _workspace_manifest())),
```

In `_background_download`, inside the `complete` branch, add:

```python
                    _model_manifest.upsert_manifest_entry(
                        _MODEL_MANIFEST_FILE,
                        _manifest_entry_from_install(url, save_path, filename),
                    )
```

- [ ] **Step 6: Add workspace, repair, export/import, and swap routes**

Add these route handlers inside the `if _server:` block:

```python
    @_server.routes.get("/comfymodal/workspaces")
    async def modal_workspaces_get(request: web.Request) -> web.Response:
        registry = _workspace_registry()
        return web.json_response({
            "status": "ok",
            "active_workspace_id": registry.get("active_workspace_id"),
            "workspaces": [_workspace_store.workspace_summary(item) for item in registry.get("workspaces", [])],
        })

    @_server.routes.post("/comfymodal/workspaces")
    async def modal_workspaces_post(request: web.Request) -> web.Response:
        body = await request.json()
        registry = _workspace_store.upsert_workspace(
            _WORKSPACES_FILE,
            body.get("label", ""),
            body.get("token_id", ""),
            body.get("token_secret", ""),
            workspace_id=body.get("workspace_id"),
            notes=body.get("notes", ""),
            set_active=bool(body.get("set_active", False)),
        )
        return web.json_response({
            "status": "ok",
            "active_workspace_id": registry.get("active_workspace_id"),
            "workspaces": [_workspace_store.workspace_summary(item) for item in registry.get("workspaces", [])],
        })

    @_server.routes.post("/comfymodal/workspaces/active")
    async def modal_workspaces_set_active(request: web.Request) -> web.Response:
        body = await request.json()
        registry = _workspace_store.set_active_workspace(_WORKSPACES_FILE, body.get("workspace_id", ""))
        return web.json_response({
            "status": "ok",
            "active_workspace_id": registry.get("active_workspace_id"),
            "workspaces": [_workspace_store.workspace_summary(item) for item in registry.get("workspaces", [])],
        })

    @_server.routes.get("/comfymodal/manifest")
    async def modal_manifest_get(request: web.Request) -> web.Response:
        manifest = _workspace_manifest()
        return web.json_response({"status": "ok", **manifest})

    @_server.routes.post("/comfymodal/manifest/repair/scan")
    async def modal_manifest_repair_scan(request: web.Request) -> web.Response:
        manifest = _workspace_manifest()
        return web.json_response({"status": "ok", "issues": _model_manifest.scan_manifest_issues(manifest)})

    @_server.routes.post("/comfymodal/manifest/repair/apply")
    async def modal_manifest_repair_apply(request: web.Request) -> web.Response:
        body = await request.json()
        repaired = _model_manifest.apply_manifest_repairs(_workspace_manifest(), body.get("updates", []))
        _model_manifest.save_master_manifest(_MODEL_MANIFEST_FILE, repaired)
        return web.json_response({
            "status": "ok",
            "entries": repaired.get("entries", []),
            "issues": _model_manifest.scan_manifest_issues(repaired),
        })

    @_server.routes.post("/comfymodal/workflow-manifest/export")
    async def modal_workflow_manifest_export(request: web.Request) -> web.Response:
        body = await request.json()
        exported = _model_manifest.export_workflow_manifest(_workspace_manifest(), body.get("prompt", {}), body.get("workflow_name", ""))
        if exported["unresolved"]:
            return web.json_response({"status": "repair_required", **exported}, status=409)
        return web.json_response({"status": "ok", **exported})

    @_server.routes.post("/comfymodal/workflow-manifest/import")
    async def modal_workflow_manifest_import(request: web.Request) -> web.Response:
        body = await request.json()
        merged = _model_manifest.merge_workflow_manifest(
            _workspace_manifest(),
            body,
            resolutions=body.get("conflict_resolutions", {}),
        )
        if merged["conflicts"]:
            return web.json_response({"status": "conflict", **merged}, status=409)
        _model_manifest.save_master_manifest(_MODEL_MANIFEST_FILE, {"manifest_version": 1, "entries": merged["entries"]})
        return web.json_response({"status": "ok", "added": merged["added"], "filled": merged["filled"]})
```

Add one background swap worker and two routes below them:

```python
    async def _run_workspace_swap_job(swap_id: str, workspace: dict):
        with _swap_jobs_lock:
            _swap_jobs[swap_id] = {"status": "running", "phase": "repairing_manifest", "workspace_label": workspace["label"]}

        manifest = _workspace_manifest()
        issues = _model_manifest.scan_manifest_issues(manifest)
        blocking = [item for item in issues if item["kind"] in {"missing_url", "missing_source_kind", "invalid_folder", "duplicate_key"}]
        if blocking:
            with _swap_jobs_lock:
                _swap_jobs[swap_id] = {"status": "repair_required", "phase": "repairing_manifest", "issues": blocking, "workspace_label": workspace["label"]}
            return

        with _swap_jobs_lock:
            _swap_jobs[swap_id]["phase"] = "downloading_models"
        remote = await get_sync_status(workspace=workspace)
        plan = _model_manifest.build_workspace_swap_plan(manifest, remote.get("models", []))
        if plan["unresolved"]:
            with _swap_jobs_lock:
                _swap_jobs[swap_id] = {"status": "repair_required", "phase": "repairing_manifest", "issues": plan["unresolved"], "workspace_label": workspace["label"]}
            return

        results = []
        if plan["to_install"]:
            results = await batch_download_models(plan["to_install"], hf_token=_read_hf_token(), civitai_token=_read_civitai_token(), workspace=workspace)
            failures = [item for item in results if item.get("status") not in {"ok", "skipped"}]
            if failures:
                with _swap_jobs_lock:
                    _swap_jobs[swap_id] = {"status": "error", "phase": "downloading_models", "failures": failures, "workspace_label": workspace["label"]}
                return

        with _swap_jobs_lock:
            _swap_jobs[swap_id]["phase"] = "syncing_custom_nodes"
        cn_result = await _sync_custom_nodes_and_maybe_deploy(os.path.join(_COMFYUI_ROOT, "custom_nodes"), workspace)
        if cn_result.get("status") != "ok":
            with _swap_jobs_lock:
                _swap_jobs[swap_id] = {"status": "error", "phase": "syncing_custom_nodes", "result": cn_result, "workspace_label": workspace["label"]}
            return

        _workspace_store.set_active_workspace(_WORKSPACES_FILE, workspace["id"])
        with _swap_jobs_lock:
            _swap_jobs[swap_id] = {
                "status": "ok",
                "phase": "deploying",
                "workspace_label": workspace["label"],
                "installed_model_count": len([item for item in results if not item.get("skipped")]),
                "skipped_model_count": len([item for item in results if item.get("skipped")]),
                "failed_model_count": 0,
                "custom_node_sync": cn_result,
                "deploy": cn_result.get("deploy"),
            }

    @_server.routes.post("/comfymodal/workspaces/swap")
    async def modal_workspace_swap(request: web.Request) -> web.Response:
        body = await request.json()
        workspace = _workspace_or_400(body.get("workspace_id", ""))
        if _deploy_status.get("state") == "deploying":
            return web.json_response({"status": "busy", "message": "deploy already running"}, status=409)
        if _ACTIVE_REQUEST_IDS and not body.get("confirm_prompt_interrupt", False):
            return web.json_response({"status": "confirm_required", "message": "prompt execution is active"}, status=409)
        swap_id = str(uuid.uuid4())
        asyncio.create_task(_run_workspace_swap_job(swap_id, workspace))
        return web.json_response({"status": "started", "swap_id": swap_id, "workspace_label": workspace["label"]})

    @_server.routes.get("/comfymodal/workspaces/swap/{swap_id}")
    async def modal_workspace_swap_status(request: web.Request) -> web.Response:
        swap_id = request.match_info.get("swap_id", "")
        with _swap_jobs_lock:
            payload = _swap_jobs.get(swap_id)
        if payload is None:
            return web.json_response({"status": "not_found", "swap_id": swap_id}, status=404)
        return web.json_response({"swap_id": swap_id, **payload})
```

- [ ] **Step 7: Run the backend tests again**

Run: `python -m unittest tests.test_modal_workspace_backend -v`

Expected: PASS

### Task 5: Update the sidebar for workspace swap and manifest tools

**Files:**
- Modify: `web/modal-settings.js:1039-2375`
- Create: `tests/test_modal_workspace_ui_ast.py`

- [ ] **Step 1: Add failing UI AST tests**

Create `tests/test_modal_workspace_ui_ast.py` with this content:

```python
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
UI_PATH = REPO_ROOT / "web" / "modal-settings.js"


class ModalWorkspaceUiAstTests(unittest.TestCase):
    def test_workspace_controls_are_present(self):
        source = UI_PATH.read_text(encoding="utf-8")
        self.assertIn("Swap Workspace", source)
        self.assertIn("Manifest Repair", source)
        self.assertIn("Export Workflow Manifest", source)
        self.assertIn("Import Workflow Manifest", source)

    def test_workspace_routes_are_called(self):
        source = UI_PATH.read_text(encoding="utf-8")
        self.assertIn("/comfymodal/workspaces", source)
        self.assertIn("/comfymodal/workspaces/swap", source)
        self.assertIn("/comfymodal/manifest/repair/scan", source)
        self.assertIn("/comfymodal/manifest/repair/apply", source)
        self.assertIn("/comfymodal/workflow-manifest/export", source)
        self.assertIn("/comfymodal/workflow-manifest/import", source)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the UI AST tests to confirm they fail**

Run: `python -m unittest tests.test_modal_workspace_ui_ast -v`

Expected: FAIL because the new controls and routes are not in `web/modal-settings.js` yet.

- [ ] **Step 3: Replace the single-token auth panel with workspace creation**

In `buildAuthPanel`, replace the existing connect button handler with a save-first-workspace flow:

```javascript
  const labelInput = document.createElement("input");
  labelInput.type = "text";
  labelInput.placeholder = "Workspace label (for the dropdown)";
  labelInput.style.cssText = inputStyle();
  wrap.insertBefore(labelInput, pasteInput);

  connectBtn.textContent = "Save Workspace";
  connectBtn.onclick = async () => {
    const label = labelInput.value.trim() || "Primary Workspace";
    const token_id = pasteInput.value.trim();
    const token_secret = tokenSecretInput.value.trim();
    errorEl.textContent = "";
    if (!token_id || !token_secret) {
      errorEl.textContent = "Workspace label, token ID, and token secret are required.";
      return;
    }
    connectBtn.disabled = true;
    connectBtn.textContent = "Saving…";
    try {
      const resp = await api.fetchApi(`${MODAL_PREFIX}/workspaces`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ label, token_id, token_secret, set_active: true }),
      });
      const data = await resp.json();
      if (data.status !== "ok") throw new Error(data.message || "Workspace save failed");
      onConnected();
    } catch (e) {
      errorEl.textContent = `Error: ${e.message}`;
      connectBtn.disabled = false;
      connectBtn.textContent = "Save Workspace";
    }
  };
```

- [ ] **Step 4: Add a new Workspace section above the current Sync section**

In `buildPanel()`, before the existing `// === SYNC SECTION` block, add:

```javascript
  let currentSwapId = null;
  let swapPollTimer = null;

  const workspaceSection = createCollapsibleSection("Workspace", { defaultOpen: true, badge: null });
  const workspaceContent = workspaceSection.content;

  const workspaceSelect = document.createElement("select");
  workspaceSelect.style.cssText = inputStyle() + "width:100%; margin-bottom:8px;";
  workspaceContent.appendChild(workspaceSelect);

  const workspaceStatus = document.createElement("div");
  workspaceStatus.style.cssText = "font-size:11px; color:#888; min-height:16px; margin-bottom:8px;";
  workspaceContent.appendChild(workspaceStatus);

  const swapBtn = document.createElement("button");
  swapBtn.textContent = "Swap Workspace";
  swapBtn.style.cssText = btnStyle("primary") + "margin-bottom:6px;";
  workspaceContent.appendChild(swapBtn);

  const repairBtn = document.createElement("button");
  repairBtn.textContent = "Manifest Repair";
  repairBtn.style.cssText = btnStyle() + "margin-bottom:6px;";
  workspaceContent.appendChild(repairBtn);

  const exportBtn = document.createElement("button");
  exportBtn.textContent = "Export Workflow Manifest";
  exportBtn.style.cssText = btnStyle() + "margin-bottom:6px;";
  workspaceContent.appendChild(exportBtn);

  const importBtn = document.createElement("button");
  importBtn.textContent = "Import Workflow Manifest";
  importBtn.style.cssText = btnStyle();
  workspaceContent.appendChild(importBtn);

  const swapProgress = document.createElement("div");
  swapProgress.style.cssText = "font-size:11px; color:#aaa; margin-top:8px; min-height:32px;";
  workspaceContent.appendChild(swapProgress);

  scrollContent.appendChild(workspaceSection.wrapper);
```

Add a loader for workspace options:

```javascript
  async function loadWorkspaces() {
    const resp = await api.fetchApi(`${MODAL_PREFIX}/workspaces`);
    const data = await resp.json();
    workspaceSelect.innerHTML = "";
    (data.workspaces || []).forEach((workspace) => {
      const opt = document.createElement("option");
      opt.value = workspace.id;
      opt.textContent = workspace.label;
      if (workspace.id === data.active_workspace_id) opt.selected = true;
      workspaceSelect.appendChild(opt);
    });
    workspaceStatus.textContent = data.workspaces?.length
      ? `Active workspace: ${workspaceSelect.options[workspaceSelect.selectedIndex]?.textContent || "none"}`
      : "No saved Modal workspaces yet.";
  }
```

- [ ] **Step 5: Add swap polling, repair modal, and export/import handlers**

Add these handlers below `loadWorkspaces()`:

```javascript
  function setWorkspaceBusy(isBusy) {
    swapBtn.disabled = isBusy;
    repairBtn.disabled = isBusy;
    exportBtn.disabled = isBusy;
    importBtn.disabled = isBusy;
    workspaceSelect.disabled = isBusy;
  }

  async function pollSwapJob() {
    if (!currentSwapId) return;
    const resp = await api.fetchApi(`${MODAL_PREFIX}/workspaces/swap/${currentSwapId}`);
    const data = await resp.json();
    if (data.status === "running") {
      swapProgress.textContent = `Phase: ${data.phase.replaceAll("_", " ")}`;
      swapPollTimer = setTimeout(pollSwapJob, 1000);
      return;
    }
    setWorkspaceBusy(false);
    if (data.status === "ok") {
      swapProgress.textContent = `${data.workspace_label}: ${data.installed_model_count} installed, ${data.skipped_model_count} skipped, deploy started.`;
      showToast("Workspace swap complete", "success");
      await loadWorkspaces();
      await loadModels();
      await loadSyncStatus();
      startDeployPoll();
      return;
    }
    if (data.status === "repair_required") {
      swapProgress.textContent = "Swap blocked: manifest repair required.";
      showToast("Manifest repair required before swap can continue", "info");
      await openManifestRepairModal(data.issues || []);
      return;
    }
    swapProgress.textContent = data.message || "Workspace swap failed.";
    showToast(data.message || "Workspace swap failed", "error");
  }

  async function openManifestRepairModal(prefetchedIssues = null) {
    const scanResp = prefetchedIssues ? null : await api.fetchApi(`${MODAL_PREFIX}/manifest/repair/scan`, { method: "POST" });
    const scanData = prefetchedIssues ? { issues: prefetchedIssues } : await scanResp.json();
    const issues = scanData.issues || [];
    if (!issues.length) {
      showToast("No manifest issues found.", "success");
      return;
    }

    const overlay = document.createElement("div");
    overlay.style.cssText = "position:fixed; inset:0; background:rgba(0,0,0,0.65); display:flex; align-items:center; justify-content:center; z-index:10001;";
    const modal = document.createElement("div");
    modal.style.cssText = "width:min(880px, 92vw); max-height:80vh; overflow:auto; background:#171717; border:1px solid #333; border-radius:8px; padding:14px;";
    const table = document.createElement("table");
    table.style.cssText = "width:100%; border-collapse:collapse; font-size:12px;";
    table.innerHTML = "<thead><tr><th style='text-align:left;'>Folder</th><th style='text-align:left;'>Filename</th><th style='text-align:left;'>Issue</th><th style='text-align:left;'>URL</th><th style='text-align:left;'>Source</th></tr></thead>";
    const body = document.createElement("tbody");
    const rows = issues.map((issue) => {
      const tr = document.createElement("tr");
      const urlInput = document.createElement("input");
      urlInput.type = "text";
      urlInput.value = issue.url || "";
      urlInput.style.cssText = inputStyle() + "width:100%;";
      const sourceSelect = document.createElement("select");
      sourceSelect.style.cssText = inputStyle() + "width:100%;";
      ["unknown", "huggingface", "civitai", "direct"].forEach((kind) => {
        const opt = document.createElement("option");
        opt.value = kind;
        opt.textContent = kind;
        if ((issue.source_kind || "unknown") === kind) opt.selected = true;
        sourceSelect.appendChild(opt);
      });
      tr.innerHTML = `<td>${issue.folder || ""}</td><td>${issue.filename || ""}</td><td>${issue.kind}</td>`;
      const urlTd = document.createElement("td");
      urlTd.appendChild(urlInput);
      const sourceTd = document.createElement("td");
      sourceTd.appendChild(sourceSelect);
      tr.appendChild(urlTd);
      tr.appendChild(sourceTd);
      body.appendChild(tr);
      return { issue, urlInput, sourceSelect };
    });
    table.appendChild(body);
    modal.appendChild(table);

    const footer = document.createElement("div");
    footer.style.cssText = "display:flex; gap:8px; justify-content:flex-end; margin-top:12px;";
    const cancelBtn = document.createElement("button");
    cancelBtn.textContent = "Cancel";
    cancelBtn.style.cssText = btnStyle();
    cancelBtn.onclick = () => overlay.remove();
    const skipAllBtn = document.createElement("button");
    skipAllBtn.textContent = "Skip All";
    skipAllBtn.style.cssText = btnStyle();
    skipAllBtn.onclick = async () => {
      const updates = rows.map(({ issue }) => ({ folder: issue.folder, filename: issue.filename, skip: true }));
      await api.fetchApi(`${MODAL_PREFIX}/manifest/repair/apply`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ updates }),
      });
      overlay.remove();
      showToast("Manifest repair skipped for selected rows.", "info");
    };
    const saveAllBtn = document.createElement("button");
    saveAllBtn.textContent = "Save All Valid";
    saveAllBtn.style.cssText = btnStyle("primary");
    saveAllBtn.onclick = async () => {
      const updates = rows
        .filter(({ urlInput }) => urlInput.value.trim())
        .map(({ issue, urlInput, sourceSelect }) => ({
          folder: issue.folder,
          filename: issue.filename,
          url: urlInput.value.trim(),
          source_kind: sourceSelect.value,
        }));
      const resp = await api.fetchApi(`${MODAL_PREFIX}/manifest/repair/apply`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ updates }),
      });
      const data = await resp.json();
      overlay.remove();
      showToast(data.issues.length ? "Manifest still has unresolved rows." : "Manifest repair saved.", data.issues.length ? "info" : "success");
    };
    footer.appendChild(cancelBtn);
    footer.appendChild(skipAllBtn);
    footer.appendChild(saveAllBtn);
    modal.appendChild(footer);
    overlay.appendChild(modal);
    document.body.appendChild(overlay);
  }

  async function openImportConflictModal(conflicts, payload) {
    const resolutions = {};
    conflicts.forEach((item) => {
      resolutions[`${item.folder}/${item.filename}`] = window.confirm(`Use imported URL for ${item.filename}?\nLocal: ${item.local_url}\nImported: ${item.imported_url}`)
        ? "use_imported"
        : "keep_local";
    });
    const resp = await api.fetchApi(`${MODAL_PREFIX}/workflow-manifest/import`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(Object.assign({}, payload, { conflict_resolutions: resolutions })),
    });
    return await resp.json();
  }

  swapBtn.onclick = async () => {
    setWorkspaceBusy(true);
    swapProgress.textContent = "Phase: repairing manifest";
    try {
      const resp = await api.fetchApi(`${MODAL_PREFIX}/workspaces/swap`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ workspace_id: workspaceSelect.value }),
      });
      const data = await resp.json();
      if (data.status === "confirm_required") {
        const ok = await showConfirm("A prompt is still running. Switch workspaces anyway?");
        if (!ok) {
          setWorkspaceBusy(false);
          swapProgress.textContent = "Swap cancelled.";
          return;
        }
        const retry = await api.fetchApi(`${MODAL_PREFIX}/workspaces/swap`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ workspace_id: workspaceSelect.value, confirm_prompt_interrupt: true }),
        });
        const retryData = await retry.json();
        currentSwapId = retryData.swap_id;
      } else {
        currentSwapId = data.swap_id;
      }
      swapProgress.textContent = "Phase: downloading models";
      pollSwapJob();
    } catch (e) {
      setWorkspaceBusy(false);
      swapProgress.textContent = `Error: ${e.message}`;
    }
  };

  repairBtn.onclick = () => openManifestRepairModal();

  exportBtn.onclick = async () => {
    const prompt = app.graph?.serialize?.() || {};
    const resp = await api.fetchApi(`${MODAL_PREFIX}/workflow-manifest/export`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ prompt, workflow_name: app.graph?.extra?.workflow?.name || "" }),
    });
    const data = await resp.json();
    if (data.status === "repair_required") {
      await openManifestRepairModal(data.unresolved || []);
      return;
    }
    const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = "workflow-manifest.json";
    link.click();
    URL.revokeObjectURL(url);
  };

  importBtn.onclick = async () => {
    const input = document.createElement("input");
    input.type = "file";
    input.accept = ".json,application/json";
    input.onchange = async () => {
      const file = input.files?.[0];
      if (!file) return;
      const payload = JSON.parse(await file.text());
      const resp = await api.fetchApi(`${MODAL_PREFIX}/workflow-manifest/import`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const data = await resp.json();
      if (data.status === "conflict") {
        const resolved = await openImportConflictModal(data.conflicts, payload);
        if (resolved.status !== "ok") throw new Error(resolved.message || "Import conflict resolution failed");
        showToast(`Import complete: ${resolved.added.length} added, ${resolved.filled.length} filled.`, "success");
        return;
      }
      showToast(`Import complete: ${data.added.length} added, ${data.filled.length} filled.`, "success");
    };
    input.click();
  };
```

Finally, call `loadWorkspaces()` near the existing startup calls at the bottom of `buildPanel()`.

- [ ] **Step 6: Run the UI AST tests again**

Run: `python -m unittest tests.test_modal_workspace_ui_ast -v`

Expected: PASS

### Task 6: Verify the full backend/manifest/workspace slice

**Files:**
- No new files

- [ ] **Step 1: Run the targeted verification suite**

Run:

```bash
python -m unittest \
  tests.test_modal_workspaces \
  tests.test_modal_client_workspaces \
  tests.test_model_manifest \
  tests.test_workflow_metadata \
  tests.test_modal_workspace_backend \
  tests.test_modal_workspace_ui_ast -v
```

Expected: PASS

- [ ] **Step 2: Run the manual verification flow from the spec**

Use this checklist:

1. Save two Modal workspaces from the sidebar.
2. Start a prompt, click **Swap Workspace**, and confirm the warning dialog appears.
3. Swap from workspace A to workspace B.
4. Confirm the progress region shows these phases in order:
   - repairing manifest
   - downloading models
   - syncing custom nodes
   - deploying
5. Confirm missing manifest-backed models are installed into workspace B.
6. Confirm custom-node sync succeeds and deploy status/logs still work.
7. Run **Manifest Repair** manually and verify missing URLs are surfaced.
8. Export a workflow manifest and inspect the JSON for absence of `token_id`, `token_secret`, workspace ids, and local secret files.
9. Import the exported manifest into another setup and confirm conflicts are surfaced instead of silently overwritten.

- [ ] **Step 3: If any targeted test fails, fix the implementation before moving on**

Use the failing test name directly, rerun only that test, and do not start broader cleanup until it passes.
