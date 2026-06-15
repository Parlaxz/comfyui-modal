# Audit: `d9f52fc` (Workspace System Init) → `2fc727e` (worsened / now)

## Commits between

```
d9f52fc Workspace System Init          ← the fast one
b01c0e0 cleanup and tightening         ← not in the "worsened" chain
c32d8f5 close production mode          ← introduced production infrastructure
6fbe499 Cleaned Safer Prodiction Mode  ← refined / expanded
2fc727e worsened.                      ← HEAD / current
```

## Per-file change summary

| File | Inserted | Deleted | Net |
|------|----------|---------|-----|
| `comfyapp.py` | +2960 | -845 | ~3765 lines changed |
| `__init__.py` | +1046 | — | ~1046 lines changed |
| `production_workflow.py` | +591 | — | **new file** |
| `output_saver.py` | +13 | — | minor |
| **Total** | **+4610** | **-845** | **~3765 net** |

---

## 1. `production_workflow.py` — ENTIRELY NEW (591 lines)

Did not exist at `d9f52fc`. Adds:

- `compile_production_workflow()` — workflow compiler that rewrites output nodes
- `normalize_production_options()` — production config normalization
- `build_production_topology_hash()` — topology fingerprinting
- `_RGTHREE_COMPARER_TARGETS = frozenset({"Image Comparer (rgthree)"})` — comparer detection
- `_OUTPUT_REWRITE_TARGETS` — SaveImage/PreviewImage rewrite rules
- `_DUPLICATE_OUTPUT_CAPABLE` — node types that support duplicate outputs
- `_topology_plan_cache` — LRU cache for compiled workflows
- Production defaults: `disable_sampler_previews`, `quiet_execution_logs`, `strict_output_collection`, `direct_output_sink`

---

## 2. `comfyapp.py` — Production node classes + encoding infra

### 2a. Two NEW remote node classes (did not exist before)

**`ComfyModalProductionOutput`** (~90 lines)
- CATEGORY `_for_internal_use/ComfyModal`
- INPUT: `images` (IMAGE tensor)
- Encodes to production format (PNG/WebP/JPEG) via Pillow
- Stores results in `_PROD_DIRECT_SINK_REGISTRY` (in-memory dict)
- Authorization gated: prompt_id must match, node_id must be in authorized set
- Returns `()` — no UI payload

**`ComfyModalProductionImageComparerOutput`** (~140 lines)
- INPUT: `image_a` (required), `image_b` (optional), `inputs_are_same` (hidden bool)
- Encodes A/B comparison images
- Tags entries with `comparison_side: "a"` or `"b"` and `output_key: "a_images"` / `"b_images"`
- Reuses encoded A for B when `inputs_are_same`
- Splits single batch into A/B when `image_b` is None but batch ≥ 2
- Stores in `_PROD_DIRECT_SINK_REGISTRY`

### 2b. New module-level registries

```python
_PROD_DIRECT_SINK_REGISTRY: dict[str, dict[str, list[dict]]] = {}
_PROD_DIRECT_SINK_REQUEST: dict | None = None
```

### 2c. New encoding helpers

- `_encode_image_tensor_batch()` — Pillow tensor→bytes encoder (PNG/WebP/JPEG)
- `_clamp_image_tensor()` — float32→uint8 clamp with range detection
- `_collect_production_request_params()` — extracts format/quality from request
- `_is_authorized_production_direct_sink_request()` — prompt_id + node_id auth gate

### 2d. Other new infrastructure (not production-specific but added in same chain)

- `_log_silent_exception()` — debug logging helper
- `PROFILING_ENABLED` flag
- `_SILENT_EXCEPTION_DEBUG` flag
- `DEFAULT_EXECUTION_BACKEND`, `ENABLE_WARMUP`, `ENABLE_TORCH_COMPILE`, `ENABLE_GPU_SNAPSHOT` flags
- `_CUSTOM_NODE_IMPORT_FAILURES` tracking
- `_CUSTOM_NODE_REGISTRATION_PENDING_RETRY` deferred retry
- Models generation control record (schema, read/write, Volume commit)
- `_convert_image_bytes()` refactor — moved from inline to standalone

---

## 3. `__init__.py` — Complex output materialization rewrite

### 3a. New production imports

```python
from production_workflow import (
    normalize_production_options,
    compile_production_workflow,
)
```

### 3b. Production workflow compilation at prompt time

In the `/comfymodal/prompt` route (was not present at `d9f52fc`):
```python
production_options = normalize_production_options(modal_options_raw)
if production_options.get("enabled"):
    compiled, production_report = compile_production_workflow(
        workflow, production_options, allow_direct_output_rewrite=False
    )
```

### 3c. Output materialization rewrite

At `d9f52fc`, output materialization was a **simple pass-through**: remote entries flowed directly to local files with preserved output-key structure.

At `2fc727e`, it's a **complex pipeline** with:

| New function/method | Purpose |
|---|---|
| `_stable_output_identity()` | Deterministic (node_id, output_key, format, index) tuple for dedup |
| `_build_materialized_output_entry()` | Wraps remote entry with `comparison_side`, `output_key`, local path |
| `_materialize_modal_outputs()` | Full rewrite with `_store_entry` closure, video detection, order tracking |
| B-priority ordering | `comparison_side == "b"` or `output_key == "b_images"` → primary |
| `b_images → images` alias | When node has `b_images` but no `images`, aliases for Media Assets |
| Animated/video tracking | `animated` flag per output key |
| `comparison_side` propagation | a/b side travels from remote through materialization to frontend |

### 3d. Ordering of output entries

At `d9f52fc`: flat iteration over `node_outputs.items()`.

At `2fc727e`: priority ordering:
1. `comparison_side == "b"` (B image first)
2. `b_images` output key entries
3. Everything else (including `comparison_side == "a"`)
4. Flat `images` entries

---

## 4. `output_saver.py` — minor

+13 lines of production-related tweaks (output key aliasing, filename format).

---

## Bottom line

| Aspect | `d9f52fc` (Workspace System Init) | `2fc727e` (worsened) |
|--------|-----------------------------------|---------------------|
| Output node classes | 0 | 2 (`ComfyModalProductionOutput`, `ComfyModalProductionImageComparerOutput`) |
| Workflow compiler | None | `production_workflow.py` (591 lines) |
| Remote image encoding | None | Pillow-based PNG/WebP/JPEG on GPU container |
| In-memory image registry | None | `_PROD_DIRECT_SINK_REGISTRY` |
| Output materialization | Simple pass-through | Complex with `comparison_side`, ordering, dedup, aliasing |
| Prompt-time compilation | None | `compile_production_workflow()` on every production prompt |
| Image format handling | Local-side only | Both remote (node classes) and local (materializer) |

The "workspace system init" era had **no production compiler, no special output node classes, and a simple output pass-through**. Everything added in the chain `c32d8f5 → 6fbe499 → 2fc727e` is production pipeline infrastructure that sits on top of the core execution path.
