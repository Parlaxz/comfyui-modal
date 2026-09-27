# Modal GPU Catalog Expansion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Expand GPU selection from 3 hardcoded options to a shared built-in Modal GPU catalog while keeping the existing frontend dropdown UX.

**Architecture:** Add a pure-data `gpu_catalog.py` module as the source of truth for GPU values, labels, class names, and resource profiles. Refactor `comfyapp.py`, `modal_client.py`, `__init__.py`, and `web/modal-settings.js` to consume that catalog, generate per-GPU Modal classes, validate config input strictly, and fetch dropdown options from the backend.

**Tech Stack:** Python 3.11, Modal, aiohttp routes in `__init__.py`, frontend JavaScript in `web/modal-settings.js`, unittest.

---

## File map

- Add: `gpu_catalog.py`
  - pure-data GPU catalog, normalization helpers, default GPU, UI option payloads
- Modify: `comfyapp.py`
  - derive supported GPUs from catalog, generate Modal classes from catalog, bump `COMFYAPP_VERSION`
- Modify: `modal_client.py`
  - derive `_apis` from catalog, strict normalization/validation, expose available GPU options
- Modify: `__init__.py`
  - return `gpu`, `default_gpu`, and `available_gpus`; reject invalid GPU POSTs with 400
- Modify: `web/modal-settings.js`
  - fetch config before initializing the dropdown, render backend-provided options, keep localStorage behavior
- Add: `tests/test_gpu_catalog.py`
  - pure import tests for catalog content, labels, default GPU, normalization
- Add: `tests/test_modal_client_gpu_config.py`
  - fake-Modal import tests for `_apis`, `set_gpu()`, and `get_available_gpus()`
- Modify: `tests/test_modal_runtime_routes.py`
  - source-level checks for config payload shape and invalid-GPU handling
- Modify: `tests/test_modal_worker_config.py`
  - source-level checks for generated class registration and preserved class names
- Add: `tests/test_modal_settings_gpu_config.py`
  - source-level checks for backend-driven dropdown setup in `web/modal-settings.js`

### Task 1: Lock in the GPU catalog behavior with failing tests

**Files:**
- Add: `tests/test_gpu_catalog.py`
- Add: `tests/test_modal_client_gpu_config.py`
- Modify: `gpu_catalog.py`
- Modify: `modal_client.py`

- [ ] **Step 1: Add pure catalog tests first**

Create `tests/test_gpu_catalog.py` with tests like:

```python
import unittest

from gpu_catalog import DEFAULT_GPU, GPU_VALUES, get_available_gpu_options, normalize_gpu_value


class GpuCatalogTests(unittest.TestCase):
    def test_default_gpu_is_a10g(self):
        self.assertEqual(DEFAULT_GPU, "a10g")

    def test_catalog_contains_expected_single_gpu_values(self):
        self.assertEqual(
            GPU_VALUES,
            [
                "t4", "l4", "a10g", "l40s", "rtx-pro-6000",
                "a100", "a100-40gb", "a100-80gb", "h100", "h200", "b200",
            ],
        )

    def test_normalize_gpu_value_lowercases_and_strips(self):
        self.assertEqual(normalize_gpu_value("  A100-80GB  "), "a100-80gb")

    def test_available_gpu_options_are_value_label_pairs(self):
        self.assertIn({"value": "a10g", "label": "A10G"}, get_available_gpu_options())
```

- [ ] **Step 2: Add fake-Modal tests for `modal_client.py`**

Create `tests/test_modal_client_gpu_config.py` that injects a fake `modal` module before importing `modal_client.py`:

```python
import importlib
import sys
import types
import unittest


class ModalClientGpuConfigTests(unittest.TestCase):
    def load_module(self):
        fake_modal = types.SimpleNamespace(
            Cls=types.SimpleNamespace(from_name=lambda app, cls: lambda: f"{app}:{cls}"),
            Function=types.SimpleNamespace(from_name=lambda app, fn: f"{app}:{fn}"),
        )
        sys.modules["modal"] = fake_modal
        sys.modules.pop("modal_client", None)
        return importlib.import_module("modal_client")

    def test_set_gpu_accepts_supported_value(self):
        mod = self.load_module()
        mod.set_gpu("L4")
        self.assertEqual(mod.get_gpu(), "l4")

    def test_set_gpu_rejects_unsupported_value(self):
        mod = self.load_module()
        with self.assertRaises(ValueError):
            mod.set_gpu("bogus")

    def test_available_gpus_come_from_catalog(self):
        mod = self.load_module()
        self.assertIn("h200", mod.get_supported_gpus())
```

- [ ] **Step 3: Run the new tests and verify they fail**

Run:

```powershell
python -m unittest tests.test_gpu_catalog tests.test_modal_client_gpu_config -v
```

Expected: import failures because `gpu_catalog.py` does not exist yet and `modal_client.py` does not expose the new strict GPU helpers.

### Task 2: Implement the shared GPU catalog and strict client validation

**Files:**
- Add: `gpu_catalog.py`
- Modify: `modal_client.py`
- Test: `tests/test_gpu_catalog.py`
- Test: `tests/test_modal_client_gpu_config.py`

- [ ] **Step 1: Add `gpu_catalog.py` as the pure source of truth**

Implement a pure-data module like:

```python
DEFAULT_GPU = "a10g"

GPU_CATALOG = [
    {"value": "t4", "label": "T4", "modal_gpu": "t4", "class_name": "ComfyAPI_T4", "profile": "budget"},
    {"value": "l4", "label": "L4", "modal_gpu": "l4", "class_name": "ComfyAPI_L4", "profile": "standard"},
    {"value": "a10g", "label": "A10G", "modal_gpu": "a10g", "class_name": "ComfyAPI", "profile": "standard"},
    {"value": "l40s", "label": "L40S", "modal_gpu": "l40s", "class_name": "ComfyAPI_L40S", "profile": "high_mem"},
    {"value": "rtx-pro-6000", "label": "RTX PRO 6000", "modal_gpu": "rtx-pro-6000", "class_name": "ComfyAPI_RTX_PRO_6000", "profile": "high_mem"},
    {"value": "a100", "label": "A100 (default 40GB)", "modal_gpu": "a100", "class_name": "ComfyAPI_A100", "profile": "high_mem"},
    {"value": "a100-40gb", "label": "A100-40GB", "modal_gpu": "a100-40gb", "class_name": "ComfyAPI_A100_40GB", "profile": "high_mem"},
    {"value": "a100-80gb", "label": "A100-80GB", "modal_gpu": "a100-80gb", "class_name": "ComfyAPI_A100_80GB", "profile": "high_mem"},
    {"value": "h100", "label": "H100", "modal_gpu": "h100", "class_name": "ComfyAPI_H100", "profile": "high_mem"},
    {"value": "h200", "label": "H200", "modal_gpu": "h200", "class_name": "ComfyAPI_H200", "profile": "high_mem"},
    {"value": "b200", "label": "B200", "modal_gpu": "b200", "class_name": "ComfyAPI_B200", "profile": "high_mem"},
]

GPU_VALUES = [entry["value"] for entry in GPU_CATALOG]

def normalize_gpu_value(gpu: str) -> str:
    return gpu.strip().lower()

def get_available_gpu_options() -> list[dict[str, str]]:
    return [{"value": entry["value"], "label": entry["label"]} for entry in GPU_CATALOG]
```

- [ ] **Step 2: Refactor `modal_client.py` to derive everything from the catalog**

Replace the handwritten `_apis` with a derived mapping:

```python
from gpu_catalog import DEFAULT_GPU, GPU_CATALOG, GPU_VALUES, get_available_gpu_options, normalize_gpu_value

_apis = {
    entry["value"]: modal.Cls.from_name("comfyui", entry["class_name"])
    for entry in GPU_CATALOG
}
_current_gpu = DEFAULT_GPU

def set_gpu(gpu: str):
    global _current_gpu
    normalized = normalize_gpu_value(gpu)
    if normalized not in _apis:
        raise ValueError(f"Unsupported GPU: {normalized}")
    _current_gpu = normalized

def get_supported_gpus() -> list[str]:
    return list(GPU_VALUES)
```

- [ ] **Step 3: Run the catalog/client tests and make them pass**

Run:

```powershell
python -m unittest tests.test_gpu_catalog tests.test_modal_client_gpu_config -v
```

Expected: PASS.

### Task 3: Lock in backend route and worker registration changes with failing tests

**Files:**
- Modify: `tests/test_modal_runtime_routes.py`
- Modify: `tests/test_modal_worker_config.py`
- Add: `tests/test_modal_settings_gpu_config.py`
- Modify: `comfyapp.py`
- Modify: `__init__.py`
- Modify: `web/modal-settings.js`

- [ ] **Step 1: Extend route tests for config payload and invalid GPU handling**

Add source-level checks in `tests/test_modal_runtime_routes.py` like:

```python
def test_config_get_route_exposes_available_gpus_and_default_gpu(self):
    source = INIT_PATH.read_text(encoding="utf-8")
    self.assertIn('"available_gpus"', source)
    self.assertIn('"default_gpu"', source)

def test_config_post_route_handles_invalid_gpu(self):
    source = INIT_PATH.read_text(encoding="utf-8")
    self.assertIn("except ValueError", source)
    self.assertIn("Unsupported GPU", source)
```

- [ ] **Step 2: Replace hardcoded class tests with generated-registration checks**

Update `tests/test_modal_worker_config.py` to assert `comfyapp.py` imports `gpu_catalog`, preserves `ComfyAPI`, and registers generated classes:

```python
def test_comfyapp_registers_gpu_classes_from_catalog(self):
    source = COMFYAPP_PATH.read_text(encoding="utf-8")
    self.assertIn("from gpu_catalog import", source)
    self.assertIn("globals()[class_name] = Generated", source)
    self.assertIn('"ComfyAPI"', source)
```

- [ ] **Step 3: Add source-level frontend tests for backend-driven options**

Create `tests/test_modal_settings_gpu_config.py` with checks like:

```python
class ModalSettingsGpuConfigTests(unittest.TestCase):
    def test_frontend_fetches_config_before_setting_gpu_options(self):
        source = SETTINGS_PATH.read_text(encoding="utf-8")
        self.assertIn("available_gpus", source)
        self.assertIn("default_gpu", source)
        self.assertNotIn("const GPU_OPTIONS = [", source)
```

- [ ] **Step 4: Run the new route/worker/frontend tests and verify they fail**

Run:

```powershell
python -m unittest tests.test_modal_runtime_routes tests.test_modal_worker_config tests.test_modal_settings_gpu_config -v
```

Expected: failure because routes, worker registration, and frontend initialization are still hardcoded.

### Task 4: Implement generated worker registration and backend config payload

**Files:**
- Modify: `comfyapp.py`
- Modify: `__init__.py`
- Test: `tests/test_modal_runtime_routes.py`
- Test: `tests/test_modal_worker_config.py`

- [ ] **Step 1: Import the catalog into `comfyapp.py` and derive compatibility constants**

Add imports/constants near the top:

```python
from gpu_catalog import DEFAULT_GPU, GPU_CATALOG, GPU_VALUES

SUPPORTED_GPUS = list(GPU_VALUES)

GPU_PROFILES = {
    "budget": {"cpu": 2, "memory": 8192, "target_inputs": 1, "max_inputs": 1},
    "standard": {"cpu": 4, "memory": 16384, "target_inputs": 1, "max_inputs": 1},
    "high_mem": {"cpu": 4, "memory": 32768, "target_inputs": 1, "max_inputs": 1},
}
```

- [ ] **Step 2: Replace the three handwritten GPU classes with a registration loop**

Add a helper near the bottom of `comfyapp.py`:

```python
def _register_gpu_classes():
    for entry in GPU_CATALOG:
        profile = GPU_PROFILES[entry["profile"]]
        class_name = entry["class_name"]
        Generated = type(class_name, (_ComfyAPIMixin,), {})
        Generated = modal.concurrent(
            target_inputs=profile["target_inputs"],
            max_inputs=profile["max_inputs"],
        )(Generated)
        Generated = app.cls(
            gpu=entry["modal_gpu"],
            cpu=profile["cpu"],
            memory=profile["memory"],
            timeout=3600,
            min_containers=0,
            scaledown_window=4,
            volumes={MODELS_PATH: vol, CUSTOM_NODES_PATH: custom_nodes_vol},
            enable_memory_snapshot=True,
            experimental_options={"enable_gpu_snapshot": True},
        )(Generated)
        globals()[class_name] = Generated


_register_gpu_classes()
```

Also bump `COMFYAPP_VERSION`.

- [ ] **Step 3: Return the full config payload and strict 400s in `__init__.py`**

Update imports and routes to use new helpers:

```python
from modal_client import ..., get_available_gpus, get_default_gpu, ...

async def modal_get_config(request):
    return web.json_response({
        "gpu": get_gpu(),
        "default_gpu": get_default_gpu(),
        "available_gpus": get_available_gpus(),
    })

async def modal_set_config(request):
    body = await request.json()
    try:
        set_gpu(body.get("gpu", ""))
    except ValueError as e:
        return web.json_response({"status": "error", "message": str(e)}, status=400)
```

- [ ] **Step 4: Run the backend/worker tests and make them pass**

Run:

```powershell
python -m unittest tests.test_modal_runtime_routes tests.test_modal_worker_config -v
```

Expected: PASS.

### Task 5: Implement frontend config-driven GPU dropdown

**Files:**
- Modify: `web/modal-settings.js`
- Test: `tests/test_modal_settings_gpu_config.py`

- [ ] **Step 1: Remove the hardcoded GPU options constant**

Delete:

```javascript
const GPU_OPTIONS = [
  { value: "a10g", label: "..." },
  { value: "a100", label: "..." },
  { value: "t4", label: "..." },
];
```

- [ ] **Step 2: Add small helpers to populate the existing `<select>` from backend config**

Implement minimal helpers:

```javascript
function setGpuOptions(selectEl, options) {
  selectEl.innerHTML = "";
  for (const opt of options) {
    const el = document.createElement("option");
    el.value = opt.value;
    el.textContent = opt.label;
    selectEl.appendChild(el);
  }
}

function pickInitialGpu(config, storedGpu) {
  const values = new Set((config.available_gpus || []).map((opt) => opt.value));
  if (storedGpu && values.has(storedGpu)) return storedGpu;
  return config.gpu || config.default_gpu || "a10g";
}
```

- [ ] **Step 3: Fetch config before initializing the dropdown**

Replace the current localStorage-first initialization with:

```javascript
const storedGpu = localStorage.getItem(STORAGE_KEY_GPU) || "";
let config = { gpu: "a10g", default_gpu: "a10g", available_gpus: [] };
try {
  const resp = await api.fetchApi(`${MODAL_PREFIX}/config`);
  config = await resp.json();
} catch {}
setGpuOptions(gpuSelect, config.available_gpus || []);
const selectedGpu = pickInitialGpu(config, storedGpu);
gpuSelect.value = selectedGpu;
window._comfyModalGpu = selectedGpu;
localStorage.setItem(STORAGE_KEY_GPU, selectedGpu);
```

Keep the existing change handler and POST sync behavior, but surface only normalized backend-supported values.

- [ ] **Step 4: Run the frontend source test and make it pass**

Run:

```powershell
python -m unittest tests.test_modal_settings_gpu_config -v
```

Expected: PASS.

### Task 6: Run the full targeted verification suite

**Files:**
- Test: `tests/test_gpu_catalog.py`
- Test: `tests/test_modal_client_gpu_config.py`
- Test: `tests/test_modal_runtime_routes.py`
- Test: `tests/test_modal_worker_config.py`
- Test: `tests/test_modal_settings_gpu_config.py`

- [ ] **Step 1: Run the focused GPU/config test suite**

Run:

```powershell
python -m unittest tests.test_gpu_catalog tests.test_modal_client_gpu_config tests.test_modal_runtime_routes tests.test_modal_worker_config tests.test_modal_settings_gpu_config -v
```

Expected: all pass.

- [ ] **Step 2: Run the existing baseline tests that touch nearby behavior**

Run:

```powershell
python -m unittest tests.test_runtime_config tests.test_module_bootstrap tests.test_modal_runtime_routes tests.test_modal_worker_config -v
```

Expected: all pass with no regressions.

- [ ] **Step 3: Check repository status**

Run:

```powershell
git status --short
```

Expected: only the planned source, test, and docs changes appear. Do not commit unless the user explicitly asks later.
