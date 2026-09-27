# RA11A — Minimal Golden Runtime and Snapshot Dependency Closure Audit

**Date:** 2026-08-30  
**Scope:** read-only architecture audit. No production source, deployment,
branch, worktree, reset, stash, cleanup, or S4/publication implementation was
changed.  
**Authority:** current source and the pinned workflow take precedence over
summaries; RA2B is used for snapshot/restore observations.  
**Repository state:** the checkout was already dirty. Existing changes were
left untouched.

## Executive conclusion

Golden can have a substantially narrower **custom-node import closure** without
creating a second runtime. The smallest coherent scope is:

1. keep the current Golden adapter and `golden_serial.py` execution contract;
2. replace “discover/import every top-level custom-node entry” with a
   Golden-profile allowlist derived from the workflow's required class IDs;
3. fail closed when a required class is not registered; and
4. defer a separate bootstrap boundary until the filtered path has measured
   value and parity evidence.

This is an architectural recommendation only. No implementation is permitted
by this audit.

The current `golden_serial.py` is already narrow at its own module boundary:
its top-level imports are standard library plus Torch, and its documented
execution path does not use the normal `PromptExecutor`. However, the Modal
composition root imports the normal V2 runtime, model preload, executor,
transport, output, tracing, and diagnostics modules before the Golden method is
called. Golden-specific imports inside that root are lazy, but the root itself
is broad. This is the principal non-custom-node closure problem.

The approximately 3.8 GB capture-to-first-restore RSS reduction is **not
explained by the module count** and is not proven to be caused by any one
Python, custom-node, Torch, CUDA, or native family. RA2B observed unchanged
mapping counts, file-backed virtual bytes, process threads, Python threads, and
FD counts, while module count increased by five. The best-supported hypothesis
is different resident-page/materialization state across the snapshot boundary,
not unloading of imported modules.

## Evidence and counting limits

### Pinned workflow identity

- Source workflow: `clean_workflow.json`.
- RA2B and Golden telemetry record **60 request nodes**.
- The current serialized `clean_workflow.json` contains **61 entries** when
  counted as a mapping. This discrepancy is retained, not hidden. One
  non-reachable candidate is `151 / ModelPatchLoader`, but the persisted
  60-node runtime payload is not available here, so the exact omitted entry
  cannot be proven from this file alone. The runtime request count remains the
  authoritative count for this report's completion field.
- Workflow hash recorded by the Golden contract and RA2B:
  `e44389ea2eda82ba5e2328acc08307b6879ed6d4ea4b030727ab044704c0d3b5`.
- Key nodes: `62 CLIPLoader`, `66 UNETLoader`, `67 CLIPTextEncode`, `1242
  ClownsharKSampler_Beta`, `1277 VAELoader`, `175 VAEDecode`, `9 SaveImage`.
  The output branch also requires `Any Switch (rgthree)`.

### Custom-node count

The workflow has **12 artifact-attributed custom-node packages**. This is a
package-owner count, not a count of imported Python modules:

| Package | Workflow class IDs evidenced |
|---|---|
| `cg-use-everywhere` | `Anything Everywhere` |
| `ComfyUI-CacheDiT` | `CacheDiT_Model_Optimizer` |
| `comfyui-custom-scripts` | `SystemNotification\|pysssss` |
| `comfyui-easy-use` | `easy float`, `easy globalSeed`, `easy ifElse`, `easy imageSize`, `easy indexAnything`, `easy int`, `easy showAnything`, `easy stringToIntList` |
| `comfyui-impact-pack` | `ImpactIfNone`, `ImpactSwitch` |
| `ComfyUI-KJNodes` | `JoinStrings`, `PathchSageAttentionKJ` |
| `comfyui-levelpixel` | `StringToCombo\|LP` |
| `comfyui_essentials` | `SimpleMath+` |
| `ComfyUI_LayerStyle` | `LayerUtility: PurgeVRAM V2` |
| `comfyui_lg_samplingutils` | `LGNoiseInjectionLatent` |
| `RES4LYF` | `ClownsharKSampler_Beta` |
| `rgthree-comfy` | `Any Switch (rgthree)`, `Image Comparer (rgthree)` |

`CustomCombo` is provided by upstream `comfy_extras/nodes_logic.py`, not by a
custom-node package. The package/class artifact `.studio_custom_nodes.json` is
dated and should be regenerated before implementation; the 12 count is
therefore exact for the inspected artifact attribution, but not a claim about
an independently regenerated deployment registry.

RA2B's `CURRENT_CUSTOM_NODE_MODULE_COUNT=951` is a derived sampled-module
family count. It is not 951 packages, and it is not a proof that 951 files were
recursively imported. The current ComfyUI loader attempts each top-level file
or directory under each configured custom-node root; each permitted package
then controls its own nested imports.

## Dependency graph

```text
Pinned workflow (60 runtime nodes; 61 serialized entries in current file)
  ├─ node class IDs / NODE_CLASS_MAPPINGS
  │    ├─ upstream core nodes and comfy_extras
  │    └─ 12 required custom-node packages
  │          └─ package __init__.py side effects
  │                └─ package submodules + third-party/native dependencies
  └─ Golden adapter: ModalRuntimeEntrypointV2.run_golden_serial_stream
       ├─ mounted runtime-state Modal Volume
       ├─ installed nodes.NODE_CLASS_MAPPINGS
       ├─ _legacy_api._ensure_gpu_ready_for_request
       ├─ activate_golden_dynamic_vram
       └─ golden_serial.golden_serial_execute
            ├─ request validation / node-map / folder_paths
            ├─ upstream comfy.sd and CLIPType
            ├─ QD safetensors source read + pinned staging + CUDA H2D
            ├─ comfy.model_detection / model_management / model_patcher / utils
            ├─ GoldenSerialRunner with selected node classes
            ├─ sampler-bound attention override (optional)
            ├─ NumPy + PIL output encoding
            ├─ Modal Volume commit + reopen/stat/read/hash proof
            └─ Golden teardown and telemetry persistence
```

The actual lifecycle is wider than this graph because `modal_app.py` is a
composition root. Its import-time surface includes contracts, deployment and
publication identity, environment and runtime shape, restore-plan machinery,
runtime executor, runtime state, model preload, CPU snapshot models, forward
probes, output/result delivery, tracing, waterfall diagnostics, teardown
diagnostics, and optionally `unet_backing`. Those imports exist even though the
Golden request does not construct an `ExecutionPlan`, call `run_plan_stream`,
use `PromptExecutor`, or use the normal V2 transport path.

## Workflow execution closure

`golden_request_setup()` validates the workflow hash, resolves the six
canonical heavy-node identities, resolves model paths through `folder_paths`,
and constructs `GoldenSerialRunner` with the already-installed
`nodes.NODE_CLASS_MAPPINGS` (`golden_serial.py:3595-3656, 3822-3889`).

The stage closure is deliberately serial:

```text
REAL RESTORE handoff observation
 → request setup / node map / paths
 → CLIP QD read, construction, adoption proof
 → CLIPTextEncode dependency closure and forward
 → UNET meta detection, QD read, assign=True adoption proof
 → sampler dependency closure (model wrappers, CacheDiT, hooks)
 → RES4LYF sampler
 → bounded sampler tail
 → VAE QD read and construction/adoption proof
 → VAEDecode dependency closure
 → selected Any Switch output branch
 → exact SaveImage-compatible PNG encode (SaveImage itself is not executed)
 → Modal Volume commit, reopen, stat, read, hash verification
 → teardown and final telemetry persistence
```

The code explicitly sequences these stages at `golden_serial.py:6811-6822`.
The output stage validates that the `SaveImage` node exists and that its image
input is the selected `Any Switch (rgthree)` branch, then performs the exact
encoding semantics itself (`golden_serial.py:6120-6331`). Therefore the package
is required for the pass-through node even though the SaveImage class itself is
upstream.

Dynamic workflow hazards remain. Node class lookup is mapping-based and node
execution follows links, so static package closure is safe only for a pinned or
validated class-ID set. Dynamic workflows, V3 extensions, custom package
entrypoints, aliases, generated classes, and package code that imports more
modules than its registered classes require a runtime discovery/validation
policy. The safe choices are: use an allowlist plus fail-closed validation for
Golden, or retain broad discovery for generic ComfyUI.

## How current custom-node discovery expands the closure

ComfyUI's `nodes.init_external_custom_nodes()` obtains every configured
`custom_nodes` root, lists its top-level entries, skips only excluded file
forms/disabled entries/policy-blocked entries, and calls `load_custom_node()`
for each remaining entry (`ComfyUI/nodes.py:2288-2323`). There is an existing
top-level allowlist mechanism: `disable_all_custom_nodes` combined with
`whitelist_custom_nodes` (`nodes.py:2312-2314`).

For a directory, `load_custom_node()` executes that directory's `__init__.py`
under a synthesized module name (`nodes.py:2192-2212`). It then registers V1
`NODE_CLASS_MAPPINGS` and display mappings or executes a V3 `comfy_entrypoint`,
`on_load()`, `get_node_list()`, and schema registration
(`nodes.py:2240-2279`). Import failures are logged and returned as failure,
not raised to abort the entire discovery loop.

Consequences:

- Discovery is broad at the top-level package boundary, not recursively
  exhaustive by ComfyUI itself.
- Registration depends on import side effects.
- Import order is observable: global mappings, display mappings, extension
  directories, and `RELATIVE_PYTHON_MODULE` are mutated; duplicate IDs can be
  order-dependent.
- A package allowlist is not a recursive import allowlist.
- `CustomNodeDiscovery` is an inventory/provenance registry. It scans
  directories and attributes already-loaded classes; it does not determine or
  enforce an import closure (`custom_node_registry.py:125-196`).
- `dependency_resolver.py:200-272` resolves required classes from metadata; it
  does not import packages and cannot prove package initialization success.

## Package `__init__` amplification audit

The 12 required packages themselves are not equally narrow:

| Package | Import behavior | Import-time side effects/resources | Closure assessment |
|---|---|---|---|
| `cg-use-everywhere` | Explicitly imports `.use_everywhere` classes and uses `comfy_entrypoint`. | Extension registration and web directory exposure. | Relatively narrow; retain package, inspect one module. |
| `ComfyUI-CacheDiT` | Imports `.nodes`, `.nodes_ltx2`, `.nodes_wan` and merges mappings. | Loads CacheDiT implementation and optional model-family surfaces. | Broad internal surface; required because the workflow enables the optimizer. |
| `comfyui-custom-scripts` | Imports `.pysssss`, then dynamically imports every top-level `py/*.py`. | Arbitrary script side effects and broad script module loading. | High-priority candidate for a class-specific Golden shim or narrower package mode; generic behavior is not statically safe. |
| `comfyui-easy-use` | Imports routes/server and about 14 node modules. | Creates wildcard/style paths and example files; rewrites `config.yaml`; startup logging. | Required classes are many, but route/server/wildcard surfaces appear non-execution-related. Strong candidate for package-level narrowing after parity proof. |
| `comfyui-impact-pack` | Wildcard-imports 12 Impact modules plus server/config. | Torch/OpenCV/NumPy/PIL/skimage/piexif imports, server load, wildcard-loading background thread, web route injection. | Significant amplification; retain only if the reachable workflow really invokes its two classes, otherwise remove from Golden closure. |
| `ComfyUI-KJNodes` | Explicitly imports many `nodes.*` modules plus optional LTXV. | Web route registration and optional import handling; includes Sage/model-optimization surfaces. | Required for `PathchSageAttentionKJ` and `JoinStrings`; optional LTXV and unrelated node modules should not be assumed required. |
| `comfyui-levelpixel` | Calls `install_init.init()` then dynamically imports 17 listed modules. | Installation/setup initialization before node imports. | Broad and side-effectful; likely removable only if `StringToCombo\|LP` can be provided without package initialization, otherwise uncertain. |
| `comfyui_essentials` | Imports seven category modules and merges mappings. | Category modules may import broad image/mask/sampling/segmentation/text dependencies. | Required for `SimpleMath+` per artifact; exact submodule closure remains uncertain. |
| `ComfyUI_LayerStyle` | Dynamically imports every `.py/*.py` module. | Directory scan; per-module side effects; permissive failure swallowing. | High amplification; required only for `LayerUtility: PurgeVRAM V2`, with package-level narrowing a likely future seam. |
| `comfyui_lg_samplingutils` | Dynamically imports every `.py/*.py` module. | Directory scan and silent per-module failure. | High amplification; required only for `LGNoiseInjectionLatent` by the pinned graph. |
| `RES4LYF` | Imports loaders/sigmas/conditioning/images/models/helper/nodes and optional extensions. | Mutates global sampler registries, registers `bong_tangent`, runs `res4lyf.init()`, may load beta/legacy/zampler extensions. | Required for the canonical sampler; registry mutation and optional extension loading make import order and compatibility critical. |
| `rgthree-comfy` | Explicit node modules plus server wildcard and optional dynamic-context nodes. | Removes old web directories and logs startup/announcement state. | Required for `Any Switch` and `Image Comparer`; server/web and unrelated nodes are likely removable only behind package-aware proof. |

The package audit did not execute these packages. Exact transitive imports,
resident mappings, thread counts, FD ownership, and registry byte sizes inside
each nested module remain unmeasured.

## Runtime service classification

| Classification | Must be retained for current Golden contract | Current evidence |
|---|---|---|
| Workflow execution | `nodes.NODE_CLASS_MAPPINGS`, `GoldenSerialRunner`, the 12 required package registrations, core `nodes`/`comfy_extras`, `folder_paths`, selected `comfy.*` model/attention helpers, NumPy/PIL output path. | `golden_serial.py:3822-3889, 4622-4719, 5374-5440, 6022-6050, 6120-6331`. |
| Model loading | Torch/CUDA, safetensors header/layout logic, QD source transport, pinned staging, CUDA H2D, `comfy.sd`, model detection, model management, model patcher, Comfy utils, retained QD owners. | `golden_serial.py:4338-4602, 5175-5368, 5836-6004`; RA2B records CLIP 8,044,936,192 B, UNET 12,309,817,472 B, VAE 335,278,732 B H2D. |
| Golden lifecycle | Modal function adapter, mounted Volume, GPU readiness check via the restored legacy API, DynamicVRAM activation, request identity, single-use teardown. | `modal_app.py:21110-21309`; adapter calls `golden_serial_execute` once. |
| Snapshot/restore | Outer Modal snapshot lifecycle and `RuntimeBootstrap` for actual restore/identity/GPU reattachment; Golden's `golden_restore` is observation only. | `runtime_bootstrap.py:1-37,1984-2044`; `golden_serial.py:3734-3819`. |
| Telemetry | Golden recorder, adapter telemetry persistence, restore boundary metadata, durable commit/reopen events. Optional deep sampling diagnostics are not execution requirements. | `golden_serial.py:696-779,6536-6670`; `modal_app.py:21161-21329`. |
| Generic ComfyUI/server/UI | HTTP/API routes, UI web extensions, manager behavior, generic prompt executor, generic history/output delivery, unrelated model libraries. | Present in the broad `modal_app.py`/`comfyapp.py` composition roots, but not called by `run_golden_serial_stream`'s Golden execution body. |
| Unrelated custom nodes | All top-level entries not needed to register the validated workflow class IDs. | Current `init_external_custom_nodes()` attempts all entries. |
| Legacy runtime | Normal V2 `ExecutionPlan`, `run_plan_stream`, `PromptExecutor`, preload/restore model machinery, generic transport and fallback branches. | Imported broadly by `modal_app.py:34-138`; Golden adapter explicitly avoids these execution paths. Some bootstrap/gpu-readiness identity remains shared and cannot be removed by assertion alone. |
| Accidental package surfaces | Eager package `__init__` imports, wildcard module loads, web/server registration, optional extensions, install/config writes. | Package audit above; ComfyUI executes each selected package `__init__.py`. |

## Import-time ownership and broad composition roots

### `comfymodal_runtime/modal_app.py`

This is the clearest source of accidental Golden closure. At module import it
loads the contracts, deployment/publication/configuration, runtime shape,
restore plan, runtime executor, runtime state, model preload, CPU snapshot
models, probes, output/result delivery, trace/waterfall, and teardown modules
(`modal_app.py:32-138`). The Golden method later uses only a thin subset:

- request validation and identity telemetry;
- a mounted runtime-state Volume;
- installed node mappings;
- isolation and GPU-readiness checks;
- DynamicVRAM activation; and
- the lazy Golden adapter call.

`golden_serial.py` is lazy-imported at `modal_app.py:21124-21129`, so it does
not add cost merely by importing `modal_app`, but the other composition-root
imports already do. A future `golden_bootstrap` could reduce this surface
without changing the Golden stage implementation.

### `comfyapp.py`

`comfyapp.py` imports Modal, configuration, deployment/publication policy,
runtime shape, and a large fail-open optimization import block at module import
(`comfyapp.py:18-210`). It is a host/legacy integration surface, not the
Golden execution engine. It remains reachable indirectly through bootstrap
helpers, generation/configuration identity, and the restored legacy API used to
ensure GPU readiness. Removing it from a dedicated Golden composition root is
plausible, but removing every dependency it provides from the lifecycle is not
yet proven.

### `model_preload.py` and `runtime_bootstrap.py`

`model_preload.py` is broad and owns normal V2 restore/preload, coordination,
model state, traces, probes, and diagnostics. Golden does not use its normal
model-preload execution path. `runtime_bootstrap.py` owns the actual restore
lifecycle, generation guards, Sage identity, and optional preload-wrapper
installation. It is a lifecycle boundary, not merely a model loader. A
dedicated bootstrap may replace the normal preload imports, but must preserve
the outer restore contract and GPU reattachment semantics.

One current contradiction is worth retaining in future work: `golden_serial.py`
documents no `comfymodal_runtime` imports (`:6-35`), but its sampling path can
dynamically import `comfymodal_runtime.runtime_executor`,
`sampling_deep_profile`, `model_preload`, and `trace` for timing/diagnostic
bridges (`:5473-5525`). These are not top-level imports and are normally
diagnostic/lifecycle compatibility paths, but they mean the no-runtime-import
claim is not absolute under every enabled configuration.

## Major imported families and resource ownership

Counts below are the defensible RA2B observations, not a full Python heap or
serialized-object census.

| Family | Count/footprint | Golden purpose | Side effects/resources observed | Verdict |
|---|---:|---|---|---|
| Python/module surface | 10,595 at capture; 10,600 first restored line; 4,000 names sampled | Broad imported runtime, ComfyUI, dependency, and custom-node surfaces. | Module count changed +5. No per-module residency attribution. | Logical narrowing is valuable, but this count cannot explain 3.8 GB RSS loss. |
| Custom-node module family | ~951 derived sampled family count | Registration and execution of the 12 package-owned class set plus unrelated registrations. | Registry size, object bytes, and per-package resident cost unknown. | Best first filter target. |
| ComfyUI/core Python | Not separately counted | Node mappings, `folder_paths`, `comfy.sd`, model detection/management/patching/utils, execution helpers. | Registries and class mappings; exact byte cost unknown. | Keep the required core closure; generic extras/UI can be outside Golden bootstrap. |
| Torch/CUDA/native | Largest virtual groups: `libcublasLt.so.13` 547,655,680 B; `libtorch_cuda.so` 397,942,784 B; `libtorch_cpu.so` 349,196,288 B; `libcufft.so.12` 291,291,136 B; NCCL 197,029,888 B | Tensor operations, CUDA runtime, allocator, model construction and transfer. | File-backed virtual bytes unchanged at 4,193,767,424 B; direct CUDA initialization/context/allocator serialization unknown. | Large address-space contributor; not proven RSS-drop cause. |
| Triton/Sage/comfy-kitchen | `libtriton.so` 180,137,984 B; comfy-kitchen extension 176,541,696 B virtual | Attention/compiler/native acceleration and Sage policy. | Loaded mappings only; no PSS/resident attribution. | Plausible residency contributor; not causally proven. |
| QD/readers/workers/futures | Capture counts all zero for tensors, QD owners, readers, preload workers, futures | Request-time model transport only. | Python threads 2, proc threads 36 at both boundaries; quiescent executor; no active QD owner at capture. | No evidence of worker leakage causing the drop. |
| ONNX Runtime | 3 database files among 19 FDs | Backend/runtime metadata. | FD count unchanged; no multi-GB attribution. | Unlikely cause. |
| Registries/coordinators | Bounded census 94 objects from 4 roots, truncated; 11 coordinators | Registry proof, lifecycle coordination, cache/ownership bookkeeping. | Direct registry bytes and complete heap graph unavailable. | Retain required registries; quantify only with a future direct census. |

RA2B paired boundary facts:

- capture VmRSS: `5,027,086,336 B`;
- first-restored-line VmRSS: `1,228,578,816 B`;
- derived difference: `-3,798,507,520 B`;
- virtual mappings: `7,989,510,144 → 8,004,837,376 B`;
- mapping count: `2,662 → 2,662`;
- file-backed mapped bytes: unchanged;
- process threads: `36 → 36`;
- Python threads: `2 → 2`;
- FDs: `19 → 19`;
- bounded capture model/QD/reader/worker/future counts: zero.

The evidence is consistent with page residency, demand paging, copy-on-write,
allocator/materialization, or serializer/lifecycle effects. It does not prove
that imported Python modules were unloaded, that native libraries were
unmapped, or that a specific custom-node package owned the missing pages.

## Explicit must-keep / likely-removable / uncertain table

| Surface | Classification | Reason |
|---|---|---|
| `golden_serial.py` stage implementation and `golden_serial_execute` | **Must keep** | Canonical serial semantics, model adoption proofs, output/durability contract. |
| `nodes.NODE_CLASS_MAPPINGS` for the validated class set | **Must keep** | Golden resolves and executes by installed mappings; missing classes must fail closed. |
| 12 package registrations listed above | **Must keep for the current pinned workflow** | The workflow references their class IDs, although their internal surfaces can be narrowed later. |
| Upstream core nodes, `comfy_extras/nodes_logic.py`, `folder_paths`, required `comfy.*` helpers | **Must keep** | Core graph semantics, model paths, model construction, decode and attention. |
| Torch/CUDA and native dependencies actually reached by selected model/attention path | **Must keep** | Model loading and inference contract. A dependency is not removable merely because its Python import is indirect. |
| Modal Volume handle/mount validation, commit, reopen/stat/read/hash | **Must keep** | True durable result contract. |
| Actual outer restore lifecycle and GPU reattachment | **Must keep** | `golden_restore` observes this; it does not replace it. |
| Golden recorder and final telemetry persistence | **Must keep** | Required evidence and lifecycle classification. |
| Top-level unrelated custom-node entries | **Likely removable from Golden import path** | Current discovery imports/attempts all top-level entries; no class in the pinned closure requires them. Generic ComfyUI must retain them. |
| Generic V2 `ExecutionPlan`/`PromptExecutor`/`run_plan_stream` path | **Likely removable from a Golden-only composition root** | Golden adapter explicitly bypasses it; keep it in the shared deployment if non-Golden requests share the process. |
| Normal model-preload implementation | **Likely removable from a dedicated Golden bootstrap** | Golden performs request-time direct loading and protects against residual preload state; outer restore identity/GPU hooks still need a replacement or narrow import. |
| Generic UI/server/manager routes and unrelated Comfy extras | **Likely removable from a dedicated Golden image/bootstrap** | Not used by the pinned Golden execution path; removal affects generic ComfyUI semantics if shared. |
| Package web registration/server imports | **Likely removable only per package** | Some are unrelated, but import side effects and V3 semantics make blanket removal unsafe. |
| `comfyapp.py` entirely | **Uncertain** | Golden does not execute it directly, but bootstrap/legacy GPU readiness and identity helpers remain reachable. |
| `runtime_bootstrap.py` entirely | **Uncertain** | Actual restore and snapshot identity are lifecycle requirements; only its normal-V2/model-preload portions are candidates. |
| Dynamic V3 entrypoints, generated classes, aliases, and unknown package imports | **Uncertain** | Static class closure cannot prove their semantics. Fail closed or retain broad discovery for dynamic workflows. |
| Torch/CUDA/Triton/Sage/native mappings | **Uncertain as snapshot optimization target** | Large mapped footprint is observed, but resident/PSS and serializer ownership are unavailable. |
| `CustomNodeDiscovery` as an allowlist authority | **Likely removable as authority** | It inventories already-loaded state; it does not calculate import closure. It may remain as provenance metadata. |

## Architecture levels

### A — current runtime plus selective custom-node import filtering

**Shape:** keep the current Modal/runtime composition root and ComfyUI
semantics, but set Golden's custom-node policy before
`init_external_custom_nodes()` so only the 12 workflow package owners (or a
smaller class-proven subset) are loaded. Validate the resulting mappings before
execution.

| Dimension | Assessment |
|---|---|
| Imported-module reduction | Potentially substantial for unrelated custom nodes; package `__init__` amplification remains. Exact reduction is unmeasured. |
| Maintainability | Best; uses an upstream-supported top-level allowlist and preserves one runtime. |
| ComfyUI upgrade compatibility | Good, but loader flags and V3 registration semantics must be rechecked per upgrade. |
| Custom-node update complexity | Low-to-medium; regenerate class/package manifest and rerun closure checks. |
| Dynamic workflow support | Limited; pinned/validated workflows only, otherwise fall back to generic discovery or reject. |
| Snapshot stability | Better if filtering occurs before capture and all selected packages are quiescent; no proof of RSS benefit yet. |
| Image reuse | Excellent; same image/runtime can serve generic ComfyUI and Golden. |
| Duplication/test burden | Lowest; test class registration, import failures, order, V1/V3, and fallback policy. |
| Divergence risk | Lowest of the three. |

### B — Golden-specific ComfyUI bootstrap sharing the current runtime

**Shape:** add a Golden bootstrap boundary that initializes only the required
ComfyUI core and filtered custom-node closure, while reusing the existing image,
Torch/CUDA/native environment, lifecycle identity, Volume contract, and proven
Golden stage implementation.

| Dimension | Assessment |
|---|---|
| Imported-module reduction | Better than A because generic V2 executor/preload/UI imports can be kept out of the Golden process/module path; native dependencies remain. |
| Maintainability | Medium; one shared runtime contract plus a new bootstrap contract. |
| ComfyUI upgrade compatibility | Medium; upstream bootstrap assumptions and registry initialization need explicit parity tests. |
| Custom-node update complexity | Medium; package allowlist and bootstrap manifest must be updated together. |
| Dynamic workflow support | Limited unless bootstrap can re-enter generic discovery; re-entry weakens the closure. |
| Snapshot stability | Better control over imported Python state, but Modal native mappings/allocator behavior still dominates unknowns. |
| Image reuse | Excellent if bootstrap is runtime selection, not a second dependency image. |
| Duplication/test burden | Medium-high; lifecycle, node registry, model path, output, V3, and generic ComfyUI parity tests. |
| Divergence risk | Medium; must prove the same upstream class registration and node semantics. |

### C — dedicated `MinimalGoldenRuntimeEntrypoint`

**Shape:** a separately composed entrypoint containing only Golden lifecycle,
filtered node registration, direct model loading, transport, output durability,
snapshot/restore identity, and required telemetry.

| Dimension | Assessment |
|---|---|
| Imported-module reduction | Maximum controllability; can test whether Python/runtime imports materially affect resident pages. |
| Maintainability | Lowest unless the boundary is kept very small and generated from explicit contracts. |
| ComfyUI upgrade compatibility | Lowest; risks replacing implicit upstream bootstrap semantics. |
| Custom-node update complexity | Highest; selected packages with broad side effects need package-specific adapters or shims. |
| Dynamic workflow support | Poor by design unless it reintroduces generic discovery. |
| Snapshot stability | Potentially best logical snapshot surface; still cannot infer native serializer behavior. |
| Image reuse | Good for the same dependency image, but separate entrypoint/import graph may require separate deployment validation. |
| Duplication/test burden | Highest; must prove output exactness, registry behavior, model adoption, restore, durability, and parity against production. |
| Divergence risk | Highest; accidental replacement of production ComfyUI semantics is the central failure mode. |

## Preferred scope

**Preferred scope: `selective-import`.**

It captures the largest low-risk architectural benefit first: unrelated
custom-node packages stop executing import-time side effects, while the
existing Golden stage, image, lifecycle, and ComfyUI semantics remain shared.
It directly addresses the proven current discovery behavior and avoids treating
the opaque RSS drop as an optimization target without causal evidence.

Level B is the next boundary only if A demonstrates a meaningful module/import
reduction and the remaining broad `modal_app.py` imports are still material.
Level C should be an investigation/measurement option, not the default product
architecture. No new runtime is justified merely by the 5 GB capture RSS
proxy.

## Verification plan before any implementation

No implementation is authorized by this report. If the scope is later approved,
the minimum evidence path is:

1. regenerate the custom-node/class registry from the exact deployment source;
2. record the 60-node runtime payload and explain the 61-entry serialized file;
3. run current generic discovery and filtered discovery in isolated processes;
4. compare registered class IDs, display mappings, `RELATIVE_PYTHON_MODULE`,
   V1/V3 outcomes, import failures, import order, extension registration, and
   workflow output SHA;
5. capture per-process module names, import wall, RSS/PSS/smaps where available,
   threads, executors, FDs, registry counts, and package side effects;
6. prove no model payload, QD owner, open reader, request worker, or future is
   present at snapshot capture;
7. compare restore-to-first-line and request-to-durable boundaries; and
8. treat any fallback, missing class, changed registry, or output mismatch as a
   failed parity result rather than silently broadening the path.

The decisive performance claim remains intentionally unproven until this
filtered A/B exists. Module reduction should be reported separately from
restore performance and from native resident-memory attribution.

## Final fields

```text
RA11A_COMPLETE=YES
WORKFLOW_NODE_COUNT=60
SERIALIZED_WORKFLOW_ENTRY_COUNT=61 (current clean_workflow.json; discrepancy documented)
REQUIRED_CUSTOM_NODE_PACKAGES=12
CURRENT_IMPORTED_MODULES_APPROX=10595
CURRENT_CUSTOM_NODE_MODULES_APPROX=951
MINIMAL_RUNTIME_FEASIBLE=YES
PREFERRED_SCOPE=selective-import
PERFORMANCE_BENEFIT_PROVEN=NO
ARCHITECTURAL_BENEFIT=HIGH
IMPLEMENTATION_PERMITTED=NO
REPORT=RA11A_MINIMAL_GOLDEN_RUNTIME_DEPENDENCY_CLOSURE_REPORT.md
```
