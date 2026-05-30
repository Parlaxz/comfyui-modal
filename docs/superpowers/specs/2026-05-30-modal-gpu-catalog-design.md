# Modal GPU Catalog Expansion Design

## Goal

Expand ComfyUI Modal GPU selection from the current handwritten 3-GPU set to a built-in catalog of Modal single-GPU identifiers, while keeping the existing frontend selection UX and making future catalog updates a one-source change.

## Current state

- `comfyapp.py` hard-codes `SUPPORTED_GPUS = ["a10g", "a100", "t4"]`.
- `comfyapp.py` also defines three separate `@app.cls(...)` runtime classes by hand: one each for `a10g`, `a100`, and `t4`.
- `modal_client.py` hard-codes a second GPU-to-Modal-class lookup and silently ignores unknown GPU values in `set_gpu()`.
- `__init__.py` exposes only the current GPU in `/comfymodal/config` and does not expose the supported list.
- `web/modal-settings.js` hard-codes a third GPU list for the dropdown.

Today, adding a GPU requires touching multiple files and risks drift between backend validation, Modal runtime dispatch, and frontend options.

## Confirmed constraints

- Use a built-in catalog, not runtime discovery from Modal.
- Scope is limited to single-GPU identifiers only.
- Keep the current frontend control pattern: a normal dropdown with the same general UX and persistence behavior.
- Do not add advanced identifiers in this change:
  - `any`
  - `H100!`
  - `B200+`
  - multi-GPU forms like `H100:2`

## Approved scope

Support this built-in GPU catalog:

- `t4`
- `l4`
- `a10g`
- `l40s`
- `rtx-pro-6000`
- `a100`
- `a100-40gb`
- `a100-80gb`
- `h100`
- `h200`
- `b200`

These values should be treated as the repo's canonical stored identifiers. Labels shown in the UI may use friendly display casing.

`a100-40gb` remains in scope as a distinct documented Modal string identifier, not as an alias for `a100`.

## Design

### Canonical GPU catalog

Define one canonical GPU catalog in a new pure-data module, `gpu_catalog.py`, that owns all GPU metadata needed by the rest of the repo.

`gpu_catalog.py` must:

- contain no `modal` imports
- contain no image/build setup side effects
- be safe to import from both `comfyapp.py` and `modal_client.py`

This avoids importing `comfyapp.py` from `modal_client.py`, which would otherwise pull in Modal app/image setup as an import side effect.

Because this repo's auto-redeploy detection is driven by `COMFYAPP_VERSION` in `comfyapp.py`, any GPU catalog change in `gpu_catalog.py` must be paired with a `COMFYAPP_VERSION` bump in `comfyapp.py`.

Each catalog entry should include at least:

- canonical stored value, e.g. `a100-80gb`
- display label for the settings dropdown
- Modal `gpu=` string to pass to `@app.cls(...)`
- deployed Modal class name
- resource profile for that GPU runtime

The catalog becomes the only place where supported GPU options are added or removed.

Recommended entry shape:

```python
{
    "value": "a100-80gb",
    "label": "A100-80GB",
    "modal_gpu": "a100-80gb",
    "class_name": "ComfyAPI_A100_80GB",
    "profile": "high_mem",
}
```

### Class naming and backward compatibility

Keep the existing deployed class name `ComfyAPI` for `a10g` so existing `Cls.from_name("comfyui", "ComfyAPI")` compatibility is preserved.

For the remaining GPUs, use a predictable explicit class naming convention:

- `t4` → `ComfyAPI_T4`
- `l4` → `ComfyAPI_L4`
- `l40s` → `ComfyAPI_L40S`
- `rtx-pro-6000` → `ComfyAPI_RTX_PRO_6000`
- `a100` → `ComfyAPI_A100`
- `a100-40gb` → `ComfyAPI_A100_40GB`
- `a100-80gb` → `ComfyAPI_A100_80GB`
- `h100` → `ComfyAPI_H100`
- `h200` → `ComfyAPI_H200`
- `b200` → `ComfyAPI_B200`

This class name should be stored directly in the catalog so `modal_client.py` can build its `Cls.from_name(...)` mapping without importing `comfyapp.py`.

### Runtime resource profiles

This repo cannot switch Modal GPU type dynamically inside one deployed class. Each supported GPU still needs its own deployed `@app.cls(...)` runtime configuration.

To remove handwritten duplication, the per-GPU runtime definitions should be generated from the canonical catalog rather than declared manually one by one.

Recommended structure:

- keep one shared `_ComfyAPIMixin`
- define a small resource-profile helper/table
- register one Modal class per supported GPU from the catalog at module import time in `comfyapp.py`
- bind each generated class into `globals()` under its catalog `class_name`
- retain a predictable mapping from canonical GPU value to deployed Modal class handle

This preserves the current deployment model while making the supported set data-driven.

Recommended registration sketch:

```python
Generated = type(class_name, (_ComfyAPIMixin,), {})
Generated = modal.concurrent(max_inputs=profile["max_inputs"])(Generated)
Generated = app.cls(
    gpu=modal_gpu,
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
```

The exact implementation can differ, but the design requires:

- module-scope registration
- deterministic class names from the catalog
- preserved `ComfyAPI` name for `a10g`
- a pre-implementation smoke test proving Modal accepts the generation pattern before broad refactoring continues

### Resource-profile policy

Resource sizing must stay explicit rather than guessed from the GPU name in scattered code.

Recommended initial profile table:

| Profile | GPUs | CPU | Memory (MB) | max_inputs |
|---|---|---:|---:|---:|
| `budget` | `t4` | 2 | 8192 | 4 |
| `standard` | `l4`, `a10g` | 4 | 16384 | 4 |
| `high_mem` | `l40s`, `rtx-pro-6000`, `a100`, `a100-40gb`, `a100-80gb`, `h100`, `h200`, `b200` | 4 | 32768 | 4 |

Preserve the current settings for existing GPUs:

- `a10g` → `standard`
- `a100` → `high_mem`
- `t4` → `budget`

Keep the profile table easy to override per GPU as real-world usage data comes in.

This change is about availability, not perfect per-GPU tuning. It is acceptable for several new GPUs to share the same initial profile family, as long as the mapping is explicit and centralized.

### Backend validation and state

`modal_client.py` should stop owning its own handwritten `_apis` truth.

Instead it should:

- import the canonical catalog from `gpu_catalog.py`
- build the GPU-to-Modal-handle mapping from catalog `class_name` values via `modal.Cls.from_name(APP_NAME, class_name)`
- expose the supported GPU list from that shared source
- normalize submitted GPU values before validation
- reject unsupported values explicitly

Normalization is exact and minimal:

- `gpu = gpu.strip().lower()`
- match only exact catalog `value` entries after normalization
- no fuzzy matching
- no implicit aliases

`set_gpu()` should no longer silently ignore bad input. It should raise `ValueError(f"Unsupported GPU: {gpu}")`, and the route layer should convert that into a `400` response.

The default GPU should remain stable and explicit. Unless there is a strong reason to change it, keep `a10g` as the default.

### Config API contract

`GET /comfymodal/config` should return the selected GPU, the default GPU, and the supported dropdown options.

Recommended response shape:

```json
{
  "gpu": "a10g",
  "default_gpu": "a10g",
  "available_gpus": [
    {"value": "t4", "label": "T4"},
    {"value": "l4", "label": "L4"}
  ]
}
```

`POST /comfymodal/config` should:

- require `gpu`
- normalize/validate it against the canonical catalog
- return `400` with a clear error message when unsupported
- return the normalized stored value on success

This keeps the backend authoritative and avoids another hard-coded frontend list.

### Frontend behavior

Keep the current GPU settings UI structure and local persistence behavior.

Change only the option source:

- remove the local 3-item `GPU_OPTIONS` constant as the authoritative source
- load `available_gpus` and `default_gpu` from `/comfymodal/config`
- render the existing dropdown from the backend-provided list
- keep storing the selected GPU in local storage as today
- keep updating `window._comfyModalGpu` as today

Initialization order matters:

1. fetch `/comfymodal/config`
2. read the stored local value
3. validate the stored value against `available_gpus`
4. if valid, use it
5. if invalid or missing, fall back to `gpu` or `default_gpu`
6. then populate the dropdown and bind change handlers

This avoids briefly rendering a stale or unsupported selection before config has loaded.

### Labels and compatibility

The frontend should continue showing friendly labels, but those labels should come from the backend-owned catalog metadata.

To avoid pricing drift, labels should not include hourly price text in the catalog. Use stable display labels only, such as:

- `T4`
- `L4`
- `A10G`
- `L40S`
- `RTX PRO 6000`
- `A100 (default 40GB)`
- `A100-40GB`
- `A100-80GB`
- `H100`
- `H200`
- `B200`

This keeps UX stable while preventing display text from drifting out of sync with the supported values.

### Explicit out-of-scope hardcoded GPUs

This change does not modify the separate `a10g` hardcoding used outside the per-user runtime selection path:

- image build step: `.run_commands(..., gpu="a10g")`
- `ui()` / web-server function: `@app.function(gpu="a10g", ...)`

Those are deployment/runtime bootstrap choices, not user-selectable generation GPUs, and remain out of scope for this change.

### Failure handling

- Unsupported GPU submitted to the config endpoint returns `400` with a message that the GPU is unsupported.
- If an old local-storage value is no longer supported, fall back to the default/current GPU and overwrite the stale local value on next successful selection sync.
- If the catalog and runtime registration ever diverge internally, fail early during module import/deploy rather than accepting a GPU that has no backing Modal class.

### Migration notes

- Keep existing deployed class names for already-supported GPUs stable:
  - `a10g` stays `ComfyAPI`
  - `a100` stays `ComfyAPI_A100`
  - `t4` stays `ComfyAPI_T4`
- New GPU classes are additive and can be deployed alongside the old set.
- `SUPPORTED_GPUS` should be removed or derived from the canonical catalog so it cannot drift.
- Any catalog change must be accompanied by a `COMFYAPP_VERSION` bump so auto-redeploy still triggers.

## Testing

Add or update tests for:

1. canonical catalog contains the approved single-GPU identifiers
2. runtime registration produces a dispatchable Modal class mapping for every supported GPU
3. `GET /comfymodal/config` returns current GPU, default GPU, and available GPU options
4. `POST /comfymodal/config` accepts valid GPU values and returns the normalized stored value
5. `POST /comfymodal/config` rejects invalid GPU values with `400`
6. frontend dropdown renders the expanded list from backend-provided options after config load
7. existing selections for `a10g`, `a100`, and `t4` still work unchanged
8. stale local-storage GPU values fall back cleanly
9. `modal_client.py` can build its mapping without importing `comfyapp.py`
10. a smoke test proves the dynamic Modal class registration pattern works for at least one newly added GPU

## Non-goals

- runtime discovery of GPU types from Modal
- advanced GPU identifiers like `any`, `H100!`, or `B200+`
- multi-GPU count forms like `A100:4`
- redesigning the GPU settings UI
- deep per-GPU cost/performance tuning beyond assigning explicit initial profiles
