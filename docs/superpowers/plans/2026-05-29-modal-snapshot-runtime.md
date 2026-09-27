# Modal Snapshot Runtime Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Modal snapshot restores nearly free, add explicit in-container runtime resync for new models/custom nodes, and add cold-start instrumentation plus requirements-install caching.

**Architecture:** Keep heavy initialization in `comfyapp.py` startup and make `restore()` avoid volume reloads, syncs, installs, and forced restarts. Add a scoped `resync_runtime()` Modal method used by backend sync routes and a new UI button, while tracking model/custom-node state plus cached requirements hashes to skip unnecessary installs.

**Tech Stack:** Python 3.11, Modal, aiohttp routes in `__init__.py`, frontend JavaScript in `web/modal-settings.js`, unittest.

---

## File map

- Modify: `comfyapp.py`
  - lifecycle hooks, runtime state helpers, requirements hash cache, resync method, timing logs
- Modify: `modal_client.py`
  - async wrapper for new runtime resync Modal method
- Modify: `__init__.py`
  - backend route for manual runtime resync, smarter post-sync refresh path, sync status enrichment
- Modify: `web/modal-settings.js`
  - resync runtime button, progress/result messaging, stale-runtime hints
- Modify: `tests/test_comfyapp_volume_lifecycle.py`
  - AST regressions for lightweight `restore()` and explicit resync method
- Add: `tests/test_comfyapp_runtime_state.py`
  - pure-Python behavior tests for requirements hashing/state helpers if helper extraction stays in `comfyapp.py`

### Task 1: Lock in the lifecycle behavior with failing tests

**Files:**
- Modify: `tests/test_comfyapp_volume_lifecycle.py`
- Add: `tests/test_comfyapp_runtime_state.py`
- Modify: `comfyapp.py`

- [ ] **Step 1: Extend the AST regression test for `restore()`**

Add tests that parse `_ComfyAPIMixin.restore` and assert it does **not** call:

```python
def _get_method(name: str):
    source = COMFYAPP_PATH.read_text(encoding="utf-8")
    module = ast.parse(source)
    for node in module.body:
        if isinstance(node, ast.ClassDef) and node.name == "_ComfyAPIMixin":
            for item in node.body:
                if isinstance(item, ast.FunctionDef) and item.name == name:
                    return item
    raise AssertionError(f"_ComfyAPIMixin.{name} not found")


def test_restore_does_not_reload_or_sync(self):
    restore = _get_method("restore")
    forbidden = {
        ("vol", "reload"),
        ("custom_nodes_vol", "reload"),
        ("self", "_sync_custom_nodes_from_volume"),
        ("self", "_restart_comfy"),
    }
    seen = {
        (node.func.value.id, node.func.attr)
        for node in ast.walk(restore)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and isinstance(node.func.value, ast.Name)
    }
    self.assertTrue(forbidden.isdisjoint(seen), seen)
```

- [ ] **Step 2: Add AST coverage for the explicit resync method**

Add a test that looks for a new `_ComfyAPIMixin.resync_runtime` method and verifies it calls stop/reload/restart primitives instead of mutating `restore()`.

```python
def test_resync_runtime_exists_and_restarts_explicitly(self):
    method = _get_method("resync_runtime")
    attrs = {
        (node.func.value.id, node.func.attr)
        for node in ast.walk(method)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and isinstance(node.func.value, ast.Name)
    }
    self.assertIn(("self", "_restart_comfy"), attrs)
```

- [ ] **Step 3: Add pure behavior tests for requirements cache/state helpers**

Create `tests/test_comfyapp_runtime_state.py` with importlib loading of `comfyapp.py` and tests like:

```python
class ComfyAppRuntimeStateTests(unittest.TestCase):
    def test_requirements_hash_changes_with_file_contents(self):
        module = load_module()
        with tempfile.TemporaryDirectory() as tmp:
            req = Path(tmp) / "requirements.txt"
            req.write_text("xformers==0.0.29\n", encoding="utf-8")
            before = module.requirements_file_hash(str(req))
            req.write_text("xformers==0.0.30\n", encoding="utf-8")
            after = module.requirements_file_hash(str(req))
            self.assertNotEqual(before, after)

    def test_missing_requirements_hash_is_none(self):
        module = load_module()
        self.assertIsNone(module.requirements_file_hash("C:/does/not/exist.txt"))
```

- [ ] **Step 4: Run targeted tests and verify they fail**

Run:

```powershell
python -m unittest tests.test_comfyapp_volume_lifecycle tests.test_comfyapp_runtime_state -v
```

Expected: failure because `restore()` still calls `_sync_custom_nodes_from_volume()` and helper functions do not exist yet.

### Task 2: Refactor `comfyapp.py` for snapshot-friendly restore and explicit runtime resync

**Files:**
- Modify: `comfyapp.py`
- Test: `tests/test_comfyapp_volume_lifecycle.py`
- Test: `tests/test_comfyapp_runtime_state.py`

- [ ] **Step 1: Add focused runtime-state helpers near the existing sync helpers**

Add helpers above `_ComfyAPIMixin` for requirements hashing and model/runtime state snapshots.

```python
import hashlib
from pathlib import Path

RUNTIME_METADATA_PATH = "/root/comfy/runtime_metadata.json"


def requirements_file_hash(path: str) -> str | None:
    if not os.path.isfile(path):
        return None
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def model_volume_state(volume_root: str) -> tuple:
    state = []
    for folder in _safe_listdir(volume_root):
        folder_path = os.path.join(volume_root, folder)
        if not os.path.isdir(folder_path):
            continue
        for name in _safe_listdir(folder_path):
            path = os.path.join(folder_path, name)
            if os.path.isfile(path):
                stat = os.stat(path)
                state.append((folder, name, stat.st_mtime_ns, stat.st_size))
    return tuple(state)
```

- [ ] **Step 2: Add metadata read/write helpers for cached requirements hashes and last-seen runtime state**

Implement tiny JSON helpers that survive within the container filesystem.

```python
def load_runtime_metadata() -> dict:
    if not os.path.isfile(RUNTIME_METADATA_PATH):
        return {"requirements": {}, "runtime": {}}
    with open(RUNTIME_METADATA_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def save_runtime_metadata(data: dict) -> None:
    os.makedirs(os.path.dirname(RUNTIME_METADATA_PATH), exist_ok=True)
    with open(RUNTIME_METADATA_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, sort_keys=True)
```

- [ ] **Step 3: Split custom-node sync from requirements installation**

Refactor `_sync_custom_nodes_from_volume()` into smaller methods so resync scopes can reuse them.

```python
def _sync_custom_nodes_from_volume(self):
    custom_nodes_vol.reload()
    summary = sync_custom_nodes_into_comfy(CUSTOM_NODES_PATH, "/root/comfy/ComfyUI/custom_nodes")
    return summary, custom_node_volume_state(CUSTOM_NODES_PATH)


def _install_custom_node_requirements(self, force: bool = False):
    metadata = load_runtime_metadata()
    cached = metadata.get("requirements", {})
    installed = []
    skipped = []
    failures = []
    ...
    return {"installed": installed, "skipped": skipped}
```

The implementation should compare `requirements_file_hash(req_file)` against cached hashes and only run pip when the hash changed or `force=True`.

- [ ] **Step 4: Make `startup()` heavy and `restore()` nearly empty**

Update lifecycle methods to do the heavy path only during snapshot creation.

```python
@modal.enter(snap=True)
def startup(self):
    ...
    vol.reload()
    _, self._custom_nodes_state = self._sync_custom_nodes_from_volume()
    install_summary = self._install_custom_node_requirements()
    self._models_state = model_volume_state(MODELS_PATH)
    self._runtime_stale = False
    self._restart_comfy()


@modal.enter(snap=False)
def restore(self):
    self._restore_started_at = time.time()
```
```

If a tiny sanity check is retained, keep it local-only and avoid reload/sync/install/restart.

- [ ] **Step 5: Add explicit runtime resync with scope support and timing logs**

Implement a new Modal method plus internal helpers.

```python
def _record_runtime_state(self):
    self._models_state = model_volume_state(MODELS_PATH)
    self._custom_nodes_state = custom_node_volume_state(CUSTOM_NODES_PATH)


@modal.method()
def resync_runtime(self, scope: str = "all"):
    started = time.time()
    if scope in {"models", "all"}:
        vol.reload()
    if scope in {"custom_nodes", "all"}:
        custom_nodes_vol.reload()
    summary = {"scope": scope}
    if scope in {"custom_nodes", "all"}:
        summary["custom_nodes"], self._custom_nodes_state = self._sync_custom_nodes_from_volume()
        summary["requirements"] = self._install_custom_node_requirements()
    if scope in {"models", "all"}:
        self._models_state = model_volume_state(MODELS_PATH)
    self._restart_comfy()
    summary["runtime_state"] = self.runtime_state()
    summary["duration_s"] = round(time.time() - started, 3)
    return {"status": "ok", **summary}
```

Also add a `runtime_state()` Modal method that compares current model/custom-node states to the last recorded in-memory states and returns `{stale, stale_reasons, models_changed, custom_nodes_changed}`.

- [ ] **Step 6: Add structured timing prints around startup/resync/prompt lifecycle**

Add minimal logging like:

```python
print(f"[comfyapp] startup sync_custom_nodes took {duration:.3f}s")
print(f"[comfyapp] resync_runtime scope={scope} took {duration:.3f}s")
print(f"[comfyapp] prompt {prompt_id} finished in {elapsed:.3f}s")
```

Keep the output concise and grep-friendly.

- [ ] **Step 7: Bump deployment version and run targeted tests**

Update:

```python
COMFYAPP_VERSION = "2.0.4"
```

Run:

```powershell
python -m unittest tests.test_comfyapp_volume_lifecycle tests.test_comfyapp_runtime_state -v
python -m py_compile comfyapp.py
```

Expected: passing targeted tests and clean syntax compilation.

### Task 3: Wire backend/client routes to the new runtime resync flow

**Files:**
- Modify: `modal_client.py`
- Modify: `__init__.py`
- Test: `tests/test_comfyapp_volume_lifecycle.py`

- [ ] **Step 1: Add Modal client wrappers for resync and runtime-state checks**

In `modal_client.py`, add wrappers:

```python
@_modal_error_handler
async def resync_runtime(scope: str = "all") -> dict:
    return await asyncio.to_thread(lambda: _api().resync_runtime.remote(scope))


@_modal_error_handler
async def get_runtime_state() -> dict:
    return await asyncio.to_thread(lambda: _api().runtime_state.remote())
```

- [ ] **Step 2: Import the new client helpers in `__init__.py` fallback/import block**

Extend the import line and fallback stubs so the server routes can call them.

```python
from modal_client import ..., refresh_custom_nodes, resync_runtime, get_runtime_state, ...

def resync_runtime(*a, **kw): raise RuntimeError("modal not installed")
def get_runtime_state(*a, **kw): raise RuntimeError("modal not installed")
```

- [ ] **Step 3: Add explicit runtime resync endpoint**

Create a new route near the existing sync endpoints.

```python
@_server.routes.post("/comfymodal/runtime/resync")
async def modal_runtime_resync(request: web.Request) -> web.Response:
    body = await request.json() if request.can_read_body else {}
    scope = body.get("scope", "all")
    if scope not in {"models", "custom_nodes", "all"}:
        return web.json_response({"status": "error", "message": "invalid scope"}, status=400)
    result = await resync_runtime(scope)
    return web.json_response(result)
```

- [ ] **Step 4: Add a runtime-state endpoint used by the UI**

Expose stale/runtime visibility separately from sync status.

```python
@_server.routes.get("/comfymodal/runtime/state")
async def modal_runtime_state(request: web.Request) -> web.Response:
    result = await get_runtime_state()
    return web.json_response(result)
```

- [ ] **Step 5: Update sync flows to use resync instead of `refresh_custom_nodes()`**

Change the existing route logic so:

```python
refresh_result = await resync_runtime("custom_nodes")
```

after custom-node upload, and optionally return a hint after model sync like:

```python
"message": "Models uploaded to Modal Volume. Run Resync Remote Runtime if the running Modal ComfyUI session does not see them yet."
```

Leave `refresh_custom_nodes()` available only if needed for backwards compatibility, but stop using it from the UI path.

- [ ] **Step 6: Run focused backend verification**

Run:

```powershell
python -m py_compile __init__.py modal_client.py comfyapp.py
python -m unittest tests.test_comfyapp_volume_lifecycle tests.test_comfyapp_runtime_state tests.test_custom_node_sync -v
```

Expected: all selected tests pass.

### Task 4: Add the runtime resync UI and stale-runtime messaging

**Files:**
- Modify: `web/modal-settings.js`
- Modify: `__init__.py`

- [ ] **Step 1: Add a resync runtime button in the Sync section**

Place it under the existing sync buttons with its own status line.

```javascript
const resyncRuntimeBtn = document.createElement("button");
resyncRuntimeBtn.textContent = "↻ Resync Remote Runtime";
resyncRuntimeBtn.title = "Reload the running Modal ComfyUI runtime so new models or custom nodes become visible";
resyncRuntimeBtn.style.cssText = btnStyle("primary") + "margin-top: 8px; margin-bottom: 4px;";
syncContent.appendChild(resyncRuntimeBtn);

const resyncRuntimeStatus = document.createElement("div");
resyncRuntimeStatus.style.cssText = "font-size: 11px; color: #888; min-height: 14px;";
syncContent.appendChild(resyncRuntimeStatus);
```

- [ ] **Step 2: Wire the button to the new backend route**

```javascript
resyncRuntimeBtn.onclick = async () => {
  resyncRuntimeBtn.disabled = true;
  resyncRuntimeBtn.textContent = "Resyncing Remote Runtime...";
  resyncRuntimeStatus.style.color = "#f5a623";
  resyncRuntimeStatus.textContent = "Stopping and restarting remote ComfyUI...";
  try {
    const resp = await api.fetchApi(`${MODAL_PREFIX}/runtime/resync`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ scope: "all" }),
    });
    const data = await resp.json();
    if (data.status !== "ok") throw new Error(data.message || "Runtime resync failed");
    resyncRuntimeStatus.style.color = "#7ed321";
    resyncRuntimeStatus.textContent = `Done in ${data.duration_s}s.`;
    showToast("Remote runtime reloaded", "success");
    await loadSyncStatus();
    await loadModels();
  } catch (e) {
    resyncRuntimeStatus.style.color = "#e05050";
    resyncRuntimeStatus.textContent = "Error: " + e.message;
    showToast("Runtime resync failed: " + e.message, "error");
  }
  resyncRuntimeBtn.disabled = false;
  resyncRuntimeBtn.textContent = "↻ Resync Remote Runtime";
};
```

- [ ] **Step 3: Surface stale-runtime hints in the Sync status panel**

After `loadSyncStatus()` or in a sibling `loadRuntimeState()`, fetch `/comfymodal/runtime/state` and append a warning banner when the running runtime is stale.

```javascript
if (runtime.stale) {
  syncStatusEl.innerHTML += `
    <div style="margin-top:8px; color:#f5a623;">
      Runtime is stale: ${runtime.stale_reasons.join(", ")}. Click <b>Resync Remote Runtime</b>.
    </div>`;
}
```

- [ ] **Step 4: Update success messages on model/custom-node sync**

Keep the current optimistic messages, but tailor them to the new resync flow.

```javascript
syncModelsStatus.textContent = data.uploaded > 0
  ? `Done! ${data.uploaded}/${data.total} model(s) uploaded. Resync Remote Runtime if the running session is stale.`
  : data.message || "All models already synced.";
```

- [ ] **Step 5: Run syntax verification for the UI**

Run:

```powershell
node --check "web/modal-settings.js"
```

Expected: no syntax errors.

### Task 5: Full verification and deployment sanity check

**Files:**
- Modify: `comfyapp.py`
- Modify: `modal_client.py`
- Modify: `__init__.py`
- Modify: `web/modal-settings.js`
- Modify/Add: `tests/...`

- [ ] **Step 1: Run focused regression suite**

Run:

```powershell
python -m unittest tests.test_comfyapp_volume_lifecycle tests.test_comfyapp_runtime_state tests.test_comfyapp_packaging tests.test_custom_node_sync tests.test_module_bootstrap tests.test_local_placeholders -v
```

Expected: all tests pass.

- [ ] **Step 2: Run syntax/compile checks**

Run:

```powershell
python -m py_compile __init__.py local_placeholders.py custom_node_sync.py modal_client.py comfyapp.py
node --check "web/modal-settings.js"
```

Expected: no output, success exit codes.

- [ ] **Step 3: Deploy manually and verify health**

Run:

```powershell
python -c "import os, subprocess, sys; p = subprocess.run(['modal','deploy','comfyapp.py'], capture_output=True, text=True, encoding='utf-8', errors='replace', env={**os.environ, 'PYTHONIOENCODING':'utf-8'}); out=(p.stdout or '') + '\n' + (p.stderr or ''); print(out.encode('ascii','replace').decode('ascii')); raise SystemExit(p.returncode)"
python -c "import modal; api = modal.Cls.from_name('comfyui','ComfyAPI')(); print(api.health.remote())"
```

Expected: deploy succeeds and health returns `{'status': 'ok'}`.

- [ ] **Step 4: Manual smoke test**

Check the UI flow manually:

1. open the Modal settings panel
2. use **Sync Models** or **Sync Custom Nodes**
3. confirm stale-runtime messaging appears when appropriate
4. click **Resync Remote Runtime**
5. confirm status refreshes and the next generation uses the refreshed runtime

Expected: new models/custom nodes become visible without redeploying or killing the whole worker.

## Plan self-review

- Spec coverage: restore no-op, model-agnostic snapshots, runtime resync, scoped resync, runtime staleness detection, requirements caching, timing instrumentation, UI button, and verification are all covered above.
- Placeholder scan: no TBD/TODO markers remain.
- Type consistency: plan uses `resync_runtime(scope: str = "all")`, `get_runtime_state()`, `requirements_file_hash()`, and `model_volume_state()` consistently.
