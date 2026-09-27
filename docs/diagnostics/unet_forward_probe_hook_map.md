# UNET Forward Probe Hook Map

> Read-only mapping. No runtime files were modified.

## HEAD SHA

```
f310ca6c5fbbf9b8f77049f75d9cf85d9f9a05d0
```

## Project layout

- **Custom node root:** `comfyui-modal/` (`custom_nodes/comfyui-modal`)
- **Pinned ComfyUI source:** `ComfyUI/` (parent directory, sibling of `custom_nodes/`)
- **Commit date:** Fri Jul 24 2026

---

## 1. Snapshot binding (CPU-snapshot UNET registration point)

### Where the CPU-snapshot UNET object is created

**File:** `comfymodal_runtime/cpu_snapshot_models.py`
**Function:** `load_cpu_snapshot_models()` (lines 721--878)

The UNET is loaded via a callback:

```python
unet_obj = load_unet(normalized["unet"], normalized.get("weight_dtype", "default"))
```

This returns a `ModelPatcher` (or `ModelPatcherDynamic`) -- the exact same type the normal loader returns. It is wrapped into a `CpuSnapshotModels` dataclass:

```python
models = CpuSnapshotModels(
    model_key=model_key,
    ...
    unet=unet_obj,       # <-- raw ModelPatcher
    clip=clip_obj,
)
```

**Dataclass definition** (line 35):

```python
@dataclass
class CpuSnapshotModels:
    model_key: ModelRestoreKey
    model_spec: dict[str, Any]
    normalized_profile: dict[str, Any]
    file_facts: tuple[ModelFileFact, ...]
    unet: Any = None          # ModelPatcher when populated
    clip: Any = None          # ModelPatcher when populated
    load_timings_ms: dict[str, float] = field(default_factory=dict)
```

### Where the snapshot UNET is activated for a request

**File:** `comfymodal_runtime/modal_app.py`
**Method:** `ComfyAPIAppBase._execute_v2_prompt_executor()` (line 2244--2520 area)

The activation happens in the `_cpu_snapshot_activated` block (around line 2484):

```python
self._use_cpu_snapshot_models_on_bridge(
    plan.model_key,
    plan.prefill_key,
    plan.model_spec,
    models.unet,          # <-- raw ModelPatcher from snapshot
    models.clip,
    trace=trace,
)
self._cpu_snapshot_models_active = True
```

### Bypass check

**File:** `comfymodal_runtime/modal_app.py`, line 2246--2313

The bypass (`diagnostic_bypass_cpu_snapshot_unet`) is a compatibility flag. When active, the snapshot block is skipped and execution falls through to the normal preload path. The check is implicit: the snapshot activation block checks `_cpu_model_snapshot_enabled()` and `self._cpu_snapshot_models is not None`. If either is false, `_cpu_snapshot_activated = False` and normal loading runs.

The `diagnostic_bypass_cpu_snapshot_unet` flag is set in `tools/benchmark_v2_direct.py` (line 167) and read in `modal_app.py`'s `_compatibility_flags`.

### The `cpu_snapshot` source vs `normal_loader` decision

The source is `cpu_snapshot` when:
1. `_cpu_model_snapshot_enabled()` returns True
2. `self._cpu_snapshot_models is not None`
3. `self._restore_plan is not None`
4. Keys and specs match between plan and snapshot

Otherwise the source is `normal_loader` (standard ComfyUI UNETLoader chain).

### UNET object available at binding point

The UNET object at the activation point (`_use_cpu_snapshot_models_on_bridge`) is the same raw `ModelPatcher` that `load_cpu_snapshot_models` produced. It was never passed through `load_models_gpu`.

---

## 2. Normal-loader return point

### Where the original UNET loader returns

**File:** `ComfyUI/comfy/sd.py`
**Function:** `load_diffusion_model_state_dict()` (line 1925, returns at line 2019)

Final return:

```python
model_patcher = ModelPatcher(model, load_device=load_device, offload_device=offload_device)
...
return model_patcher
```

Where `ModelPatcher` is resolved as:
```python
ModelPatcher = comfy.model_patcher.ModelPatcher if disable_dynamic else comfy.model_patcher.CoreModelPatcher
```

(`CoreModelPatcher` does **not exist** in this pinned ComfyUI at `model_patcher.py` line 292+. Either `disable_dynamic=True` is always passed, or the code catches `AttributeError`. The concrete class is `ModelPatcher`.)

**Wrapper function** `load_diffusion_model()` (line 2022):

```python
def load_diffusion_model(unet_path, model_options={}, disable_dynamic=False):
    sd, metadata = comfy.utils.load_torch_file(unet_path, return_metadata=True)
    model = load_diffusion_model_state_dict(sd, model_options=model_options, metadata=metadata, disable_dynamic=disable_dynamic)
    ...
    return model     # <-- raw ModelPatcher
```

### Returned object shape

`ModelPatcher` (file: `ComfyUI/comfy/model_patcher.py`, line 292):

```
ModelPatcher
  .model          -> BaseModel (torch.nn.Module) with .diffusion_model -> NextDiT
  .load_device    -> torch.device
  .offload_device -> torch.device
  .patches        -> dict
  .backup         -> dict
  .model_options  -> dict (includes transformer_options)
  .patches_uuid   -> UUID
  .parent         -> ModelPatcher | None
  .is_dynamic()   -> bool (False for ModelPatcher, True for ModelPatcherDynamic)
  .model_patches_models() -> list[ModelPatcher]
```

### Whether the normal-loader bypass passes through this function

Yes. The V2LoaderBridge wrapper intercepts `UNETLoader.load_unet` and returns a pre-loaded model from the bridge's future (which was populated from the cpu_snapshot). The normal loader (`load_diffusion_model` / `load_diffusion_model_state_dict`) is **not called** during the request when cpu_snapshot is active. When the bridge returns `_LOADER_MISS` (no prepared model), the original `UNETLoader.load_unet` runs, which eventually calls `load_diffusion_model`.

---

## 3. Existing `load_models_gpu` wrapper

### File and wrapper function

**File:** `comfymodal_runtime/model_preload.py`
**Function:** `_make_gpu_loader_wrapper()` (line 290)
**Installation:** `_install_gpu_wrapper()` (line 1300) patches `comfy.model_management.load_models_gpu`

There is also a **second wrapper** in `comfymodal_runtime/runtime_executor.py`:

**File:** `comfymodal_runtime/runtime_executor.py`
**Function:** `_patched_load_models_gpu()` (line 1325)

This second wrapper is installed only when `_instrumentation_var` is set (for pre-sampler instrumentation).

### Outermost/reentrancy guard

**Yes**, both wrappers use a reentrancy guard:

1. **`_make_gpu_loader_wrapper`** uses `_gpu_depth` (ContextVar, line 164):
   ```python
   before = _gpu_depth.get()
   _gpu_depth.set(before + 1)
   ...
   if before == 0:
       # outermost call -- emit events
   ...
   _gpu_depth.set(after - 1)
   ```

2. **`_patched_load_models_gpu`** uses `_instrumentation_var`:
   ```python
   state = _instrumentation_var.get()
   if state is None:
       return _orig_load_models(...)   # bypass, no instrumentation
   ```

### Existing active request trace ContextVars

Defined in `comfymodal_runtime/model_preload.py`:

| ContextVar | Type | Purpose |
|---|---|---|
| `_ACTIVE_LANE_TRACE` | `ContextVar["ModelLaneTrace \| None"]` (line 115) | Set during worker callback execution |
| `_ACTIVE_REQUEST_TRACE` | `ContextVar["RuntimeTrace \| None"]` (line 118) | Set for each request via `request_execution_trace_scope()` |
| `_ACTIVE_V2_LOADER_BRIDGE` | `ContextVar["V2LoaderBridge \| None"]` (line 4131) | Set during bridge `request_scope()` |
| `_gpu_depth` | `ContextVar[int]` (line 164) | Reentrancy counter for GPU loader wrapper |
| `_gpu_request_call_count_var` | `ContextVar[int]` (line 186) | Per-request GPU call counter |

The `_ACTIVE_REQUEST_TRACE` is set at `modal_app.py:3098`:
```python
with request_execution_trace_scope(trace):
    with self._preload_bridge.request_scope():
        result = await self._execute_v2_prompt_executor(...)
```

### Shape of `models` argument elements

The `load_models_gpu` function in `ComfyUI/comfy/model_management.py` (line 843) receives a list of models that are **always `ModelPatcher` instances**. This is verified by:

1. The function's first operation:
   ```python
   for m in models:
       models_temp[m] = None
       for mm in m.model_patches_models():   # ModelPatcher method
           models_temp[mm] = None
   ```

2. The function then wraps each in `LoadedModel`:
   ```python
   loaded_model = LoadedModel(x)   # x is always ModelPatcher
   ```

3. `LoadedModel.__init__` (line 677--684):
   ```python
   class LoadedModel:
       def __init__(self, model: ModelPatcher):
           self._set_model(model)
           self.device = model.load_device
           ...
   ```

**Conclusion:** Every element in the `models` argument is a `ModelPatcher` (or `ModelPatcherDynamic` -- a subclass). There is no `LoadedModel` or other wrapper in the outer list. `LoadedModel` wraps each element **inside** `load_models_gpu`.

### Field path to resolve the underlying ModelPatcher

No resolution needed -- each element **is** a `ModelPatcher` directly.

---

## 4. `NextDiT.forward`

### Class module and qualname

```
comfy.ldm.lumina.model.NextDiT
```

**File:** `ComfyUI/comfy/ldm/lumina/model.py`

- `NextDiT` - line 423
- `NextDiTPixelSpace(NextDiT)` - line 972

### Base class

```python
class NextDiT(nn.Module):   # line 423
```

### Forward method signature (line ~916)

```python
def forward(self, x, timesteps, context, num_tokens, attention_mask=None, **kwargs):
    return comfy.patcher_extension.WrapperExecutor.new_class_executor(
        self._forward,
        self,
        comfy.patcher_extension.get_all_wrappers(
            comfy.patcher_extension.WrappersMP.DIFFUSION_MODEL,
            kwargs.get("transformer_options", {})
        )
    ).execute(x, timesteps, context, num_tokens, attention_mask, **kwargs)
```

The actual implementation is `_forward` (line ~923):

```python
def _forward(self, x, timesteps, context, num_tokens, attention_mask=None,
             ref_latents=[], ref_contexts=[], siglip_feats=[],
             transformer_options={}, **kwargs):
```

### Primary latent/sample tensor argument

**`x`** -- 1st positional parameter.

Type: `torch.Tensor`. Shape at dispatch: `(batch, channels, height, width)` -- the noise/latent input.

It is called from `BaseModel._apply_model` (`ComfyUI/comfy/model_base.py`, line ~231):

```python
model_output = self.diffusion_model(xc, t, context=context, control=control,
                                     transformer_options=transformer_options, **extra_conds)
```

Here `xc` is the processed latent, `t` is timesteps, `context` is cross-attention (text embeddings).

### Positional vs keyword calling convention

**Positional.** The actual call in `_apply_model` passes `xc` positionally as `x`:

```python
self.diffusion_model(xc, t, context=context, ...)
```

So the first positional argument (`x`) is the latent tensor, second (`timesteps`) is the timesteps, third (`context`) is text embeddings.

### Whether `register_forward_pre_hook` is available

**Yes.** `NextDiT` is a `torch.nn.Module` subclass. All standard PyTorch hook APIs are available:

- `register_forward_pre_hook(hook)`
- `register_forward_hook(hook)`
- `register_full_backward_pre_hook(hook)`
- `register_full_backward_hook(hook)`

These work for any `nn.Module`.

### Whether hooks receive kwargs in this pinned PyTorch version

**Depends on PyTorch version.** `register_forward_pre_hook` with `with_kwargs=True` was added in PyTorch 2.1 (stable release). For a basic pre-hook that only inspects the input tensor, the standard `register_forward_pre_hook(hook)` is sufficient -- it receives `(module, args)`. To receive kwargs as well, use prepend with `with_kwargs=True`:

```python
def pre_hook(module, args, kwargs):
    x = args[0]
    # inspect x
    return args, kwargs  # or modified args/kwargs
```

The standard hook (without `with_kwargs=True`) does **not** receive kwargs.

---

## 5. Request trace and source correlation

### Active ContextVars during phases

| Phase | Active ContextVar(s) |
|---|---|
| `load_models_gpu` | `_ACTIVE_REQUEST_TRACE` (set via `request_execution_trace_scope`), `_ACTIVE_LANE_TRACE` (set by worker lane context), `_ACTIVE_V2_LOADER_BRIDGE` |
| `NextDiT.forward` | Same `_ACTIVE_REQUEST_TRACE` (same async context -- `request_execution_trace_scope` wraps the entire `_execute_v2_prompt_executor` call) |

### Available trace fields

`RuntimeTrace` (file: `comfymodal_runtime/trace.py`, line 49):

```python
class RuntimeTrace:
    def __init__(self, *, request_id: str, container_session_id: str, process: str, trace_id: str):
        self.request_id           # str - the request identifier
        self.container_session_id # str - container session identifier
        self.process              # str - "local"/"remote_method"/etc.
        self.trace_id             # str - auto-generated hex UUID[:16]
```

Additional metadata available via `trace._metadata` dict:

| Key | Set by |
|---|---|
| `"restored_instance_id"` | `set_model_load_identity()` in `model_preload.py:2215` |
| `"restore_session_id"` | `set_model_load_identity()` in `model_preload.py:2215` |
| `"container_task_id"` | Modal container environment |
| `"modal_input_id"` | Modal input ID |
| `"image_id"` | Modal image ID |
| `"cloud"`, `"region"` | Modal deployment metadata |
| `"app_name"`, `"class_name"`, `"method_name"` | Modal app identity |
| `"workflow_hash_prefix"` | Workflow hash |
| `"restore_plan_generation"` | Restore plan generation |
| `"lane"` | Current lane (UNET/CLIP/VAE) |
| `"canonical_key_hash"` | Model identity key hash |

### Module-level globals for restore identity

```python
# comfymodal_runtime/model_preload.py:2215
_LATEST_RESTORED_INSTANCE_ID: str = ""
_LATEST_RESTORE_SESSION_ID: str = ""
```

These are set by `set_model_load_identity()` and read by the GPU wrapper to propagate restore context into commit events.

### Storage location for diagnostic-only mappings

**Recommendation:** Store diagnostic mappings (diffusion-model identity -> ModelPatcher, source type) on the `RuntimeTrace._metadata` dict, keyed by `"diagnostic_diffusion_model_map"`. This is already the established pattern for per-request diagnostic data in this codebase.

The trace is accessible during both `load_models_gpu` (via `_ACTIVE_REQUEST_TRACE.get()`) and `NextDiT.forward` (still in the same `request_execution_trace_scope`).

Alternatively, use a new module-level `ContextVar[dict]` (`diagnostic_model_patcher_map`) scoped to the request, set up alongside `request_execution_trace_scope`.

---

## 6. Recommended hook insertion points

### Hook A: UNET state after `load_models_gpu()` outermost return

**Insertion point:** Inside `_make_gpu_loader_wrapper` (model_preload.py line 374), **after** `original(models, ...)` returns and **before** the reentrancy guard decrement (line 379).

Specifically, in the `try/finally` block, right after:
```python
return original(models, memory_required=memory_required, ...)
```
and right before:
```python
finally:
    after = _gpu_depth.get()
    _gpu_depth.set(after - 1)
    if before == 0:
        ...
```

Place the hook inside the `if before == 0:` block, after the existing `lane.gpu_commit_end()` call. At this point:
- `models` contains the actual `ModelPatcher` instances
- The UNET ModelPatcher's `.model` (BaseModel) has `.diffusion_model` (NextDiT) loaded on GPU
- The `_ACTIVE_REQUEST_TRACE` is still set

### Hook B: UNET state before `NextDiT.forward()` first call

**Insertion point 1 (recommended - pre-hook on nn.Module):**

Use `NextDiT.register_forward_pre_hook()`.

```
comfy.ldm.lumina.model.NextDiT  (class)
```

Install during warmup/bootstrap. The hook function receives `(module, args)` where `args[0]` is the latent tensor `x`.

**Installation location:** In a `@classmethod` or top-level function called once at module import time (or inside an `_ensure_diagnostics_wrappers()` pattern similar to `_install_gpu_wrapper` at `model_preload.py:1300`).

```python
_nextdit_original_forward = NextDiT.forward

@functools.wraps(NextDiT.forward)
def _nextdit_diagnostic_forward(self, x, timesteps, context, num_tokens, attention_mask=None, **kwargs):
    # -- capture pre-forward state here --
    # access trace via _ACTIVE_REQUEST_TRACE.get()
    # access ModelPatcher via diagnostic ContextVar
    return _nextdit_original_forward(self, x, timesteps, context, num_tokens, attention_mask, **kwargs)

NextDiT.forward = _nextdit_diagnostic_forward
```

This patching approach works because `NextDiT.forward` is a plain method (not a wrapped method from the start). It already delegates through `WrapperExecutor` internally, so adding an outer wrapper is safe.

**Insertion point 2 (alternative - monkey-patch `BaseModel._apply_model`):**

At `ComfyUI/comfy/model_base.py` line ~231, before:
```python
model_output = self.diffusion_model(xc, t, context=context, ...)
```

This is where the diffusion model's forward is called. However, this is inside the patcher_extension.WrapperExecutor chain, making it harder to isolate.

### Recommended approach

1. **Install a forward_pre_hook** on `comfy.ldm.lumina.model.NextDiT` (class-level `register_forward_pre_hook`).
2. **In the hook function**, capture `args[0]` (the `x` tensor) and correlate it to the ModelPatcher using a `ContextVar[dict[int, Any]]` keyed by `id(self)`.
3. **Populate the correlation dict** in the `_make_gpu_loader_wrapper` after `original(models)` returns (Hook A location above).

---

## 7. Remaining uncertainty

1. **`CoreModelPatcher`**: The codebase references `comfy.model_patcher.CoreModelPatcher`, but it does not exist in the pinned ComfyUI's `model_patcher.py`. It may have been removed or aliased dynamically. The `sd.py:2018` conditional `ModelPatcher = comfy.model_patcher.ModelPatcher if disable_dynamic else comfy.model_patcher.CoreModelPatcher` may always take the `disable_dynamic=True` branch or may fail to `AttributeError` (caught upstream). For safety, treat the return type as always `ModelPatcher`.

2. **NextDiT field presence**: The `NextDiT` instance inside `ModelPatcher.model.diffusion_model` was verified via `model_base.py:231` (`self.diffusion_model(xc, ...)`). But the `ModelPatcher.model` field is typed as `Any` (BaseModel). The exact `.diffusion_model` attribute path is:
   ```
   ModelPatcher.model.diffusion_model -> NextDiT (nn.Module)
   ```

3. **PyTorch hook kwargs support**: Whether `with_kwargs=True` is available depends on PyTorch version (>= 2.1). The standard pre-hook (no kwargs) is guaranteed.

4. **Hook installation timing**: The `load_models_gpu` wrapper is installed during `_ensure_core_wrappers()` → `_install_gpu_wrapper()`. The NextDiT forward hook must be installed before the first request. The existing `_ensure_core_wrappers()` pattern is the correct integration point.

---

## 8. Minimal implementation contract for the runtime-wiring agent

### What the wiring agent must do

1. **Add a diagnostic ContextVar** at module level in `model_preload.py`:
   ```python
   _DIAGNOSTIC_MODEL_MAP: ContextVar[dict[int, tuple[Any, str]]] = ContextVar(
       "_diagnostic_model_map", default={}
   )
   # key = id(ModelPatcher.model.diffusion_model)
   # value = (ModelPatcher, source_type)
   # source_type = "cpu_snapshot" | "normal_loader"
   ```

2. **Populate the map** inside `_make_gpu_loader_wrapper` (model_preload.py), in the `if before == 0:` block after `original(models)` returns. Iterate `models`, for each with a `.model.diffusion_model`, store:
   ```python
   dm = model.model.diffusion_model
   _map[id(dm)] = (model, source_type)
   ```

3. **Install a forward pre-hook** on `NextDiT` (class `comfy.ldm.lumina.model.NextDiT`). In the hook body:
   - Read `_DIAGNOSTIC_MODEL_MAP.get()` using `id(self)`  
   - Read `_ACTIVE_REQUEST_TRACE.get()` to get the RuntimeTrace
   - Emit a diagnostic event with the tensor shape, ModelPatcher identity, and source type
   - Read `args[0]` for the latent tensor

4. **Determine `source_type`**: In the outer wrapper's scope, when the bridge's pre-loaded model is used (cpu_snapshot source), the `_ACTIVE_V2_LOADER_BRIDGE` ContextVar is set. Detect it:
   - `source_type = "cpu_snapshot"` if `_ACTIVE_V2_LOADER_BRIDGE.get()` is not None
   - `source_type = "normal_loader"` otherwise

5. **Register the hook** during bootstrap alongside the existing `_install_gpu_wrapper` call (model_preload.py line 1351 area).

### Files that need read-only changes (read-only mapping only -- do not edit)

- **`comfymodal_runtime/model_preload.py`** -- ContextVar, GPU wrapper integration, hook registration
- **`comfy/ldm/lumina/model.py`** -- `NextDiT.forward` signature reference (no edits needed)
- **`comfymodal_runtime/trace.py`** -- `RuntimeTrace` for trace emission

### Files that must NOT be modified

- No runtime edits to `ComfyUI/comfy/` files
- No test file modifications
- No schema/contract changes

---

## Summary table

| Item | Location |
|---|---|
| **HEAD** | `f310ca6c5fbbf9b8f77049f75d9cf85d9f9a05d0` |
| **Snapshot UNET creation** | `comfymodal_runtime/cpu_snapshot_models.py:721` (`load_cpu_snapshot_models`) |
| **Snapshot UNET activation** | `comfymodal_runtime/modal_app.py:2484` (`_use_cpu_snapshot_models_on_bridge`) |
| **Normal loader return** | `ComfyUI/comfy/sd.py:2019` (`load_diffusion_model_state_dict` returns `ModelPatcher`) |
| **ModelPatcher class** | `ComfyUI/comfy/model_patcher.py:292` (`class ModelPatcher`) |
| **load_models_gpu wrapper** | `comfymodal_runtime/model_preload.py:290` (`_make_gpu_loader_wrapper`) |
| **load_models_gpu original** | `ComfyUI/comfy/model_management.py:843` (`def load_models_gpu`) |
| **Outermost guard** | `model_preload.py:303-304` (`_gpu_depth` ContextVar) |
| **Request trace ContextVar** | `model_preload.py:118` (`_ACTIVE_REQUEST_TRACE`) |
| **Models arg shape** | Always `list[ModelPatcher]` (no other wrappers in the list) |
| **NextDiT class** | `ComfyUI/comfy/ldm/lumina/model.py:423` (`class NextDiT(nn.Module)`) |
| **NextDiT.forward** | `model.py:916` (`def forward(self, x, timesteps, context, num_tokens, attention_mask=None, **kwargs)`) |
| **Primary tensor argument** | `x` (1st positional, type `torch.Tensor`, the latent/noise) |
| **Call convention** | Positional (`self.diffusion_model(xc, t, context=context, ...)`) |
| **Hook support** | Yes (`nn.Module`, `register_forward_pre_hook` available) |
| **Hook kwargs** | Standard pre-hook receives `(module, args)` only; use `with_kwargs=True` for kwargs support (PyTorch >= 2.1) |
