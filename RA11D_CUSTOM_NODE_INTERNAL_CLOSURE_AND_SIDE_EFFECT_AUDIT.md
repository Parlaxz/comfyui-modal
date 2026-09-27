# RA11D — Custom-Node Internal Closure and Import Side-Effect Audit

**Date:** 2026-08-30  
**Scope:** read-only inspection of the installed custom-node trees used by the
current main ComfyUI worktree. Only this report was created. No runtime,
configuration, test, custom-node source, package environment, branch, worktree,
deployment, or Modal state was changed.

## 1. Executive findings

1. The candidate universe contains **12 installed package trees**. The current
   `.studio_custom_nodes.json` artifact attributes the current fixture to all
   12, but its package/class inventory is stale or internally inconsistent in
   places; it is not an independently regenerated runtime registry.
2. The fixture has **21 explicit package-owned class IDs** in the inspected
   attribution table. This is a class-attribution count, not an execution
   count. RA11C owns the semantic determination of executed, validation-only,
   registration-only, and global-side-effect roles.
3. Package entrypoints are materially different. `comfyui_essentials` has a
   finite seven-category eager import; `comfyui-custom-scripts`, LevelPixel,
   LayerStyle, and `comfyui_lg_samplingutils` enumerate/import child modules;
   RES4LYF and several other packages perform process-global registration or
   hooks during initialization.
4. The largest proven import amplification is in `comfyui-easy-use`,
   `comfyui-impact-pack`, `ComfyUI-KJNodes`, `ComfyUI_LayerStyle`, RES4LYF,
   `rgthree-comfy`, LevelPixel, and custom-scripts. This is a source-structure
   classification only; no import timing, RSS, PSS, restore, or E2E savings are
   claimed.
5. The highest correctness risks are:
   - RES4LYF sampler/scheduler table mutation and reload;
   - cg-use-everywhere frontend graph-global preprocessing;
   - easy-use model-path/prompt/server initialization;
   - Impact’s server import and startup wildcard thread;
   - LevelPixel’s import-time filesystem bootstrap; and
   - rgthree route/web/cache behavior.
6. A directly importable class module is **not** shown to be equivalent to
   normal package initialization. Package metadata must describe the initializer
   and global-hook closure separately from the class definition.
7. This report does **not** recommend a Golden runtime, a Golden-only
   allowlist, a `golden_p1` import branch, package deletion, package
   uninstallation, or an environment permanently initialized for this fixture.
   Golden is the first deeply studied fixture for a future **generic,
   workflow-driven** resolver used by the same runtime for arbitrary workflows.

### Correct generic target

```text
incoming workflow
  -> resolve class/alias/V1/V3/global/preprocessing semantics
  -> derive required initializer/import/global-hook closure
  -> initialize only closure minus the process-initialized set
  -> validate registration and global behavior
  -> execute
```

The installed/published environment remains complete. The process-initialized
set grows monotonically; registrations are not unloaded or undone underneath a
later workflow. If a bounded closure cannot be proven, the resolver must use
the existing complete discovery path and fail if required registration is still
missing. A package’s fixture findings are reusable metadata candidates, not a
universal package allowlist.

## 2. Methodology and evidence limitations

### Inspected authority

- Current Golden source: `comfymodal_runtime/golden_serial.py`.
- Pinned fixture: `clean_workflow.json`.
- Attribution artifact: `.studio_custom_nodes.json`.
- Current closure context: `RA11A_MINIMAL_GOLDEN_RUNTIME_DEPENDENCY_CLOSURE_REPORT.md`.
- Remote baseline context: `RV2B_REMOTE_GOLDEN_BASELINE_TRUTH_REPORT.md`.
- Current ComfyUI discovery: `ComfyUI/nodes.py`.
- Installed package trees: sibling directories under
  `C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes`.

The codebase-memory index covers `comfyui-modal`, not the sibling installed
package trees. Package conclusions therefore use direct source inspection and
the exact paths listed below. The indexed project reported one unrelated
fixture parse-partial file and one skipped report; neither is used as package
source evidence.

### What was not done

- No package was imported in the main process or a subprocess.
- No installer, prestartup installer, download, network request, subprocess,
  thread probe, or dynamic import trace was executed.
- No package source or configuration was patched.
- No Modal deploy or request was made.

Consequently, dynamic optional dependencies, actual import success, import
order under the host, route registration against a live server, resource
counts, and runtime model/cache behavior remain `UNKNOWN` unless source proves
the behavior itself. “Absent statically” is not proof that dependency internals
cannot create the resource.

### Confidence vocabulary

- **PROVEN:** directly established by current source or an explicit artifact.
- **SUPPORTED:** strong source-supported inference with a bounded limitation.
- **UNKNOWN:** dynamic, environment-dependent, unexecuted, contradictory, or
  otherwise not established.

The A–F narrowing labels below mean:

| Label | Meaning |
|---|---|
| A | Package import is already narrow relative to its exposed surface. |
| B | Package-level filtering/allowlisting can capture most available benefit. |
| C | A class/module-specific seam is plausible without bypassing required semantics. |
| D | A small package-specific bootstrap/shim may reproduce required state. |
| E | Narrowing is unsafe without upstream/package-aware modification or stronger proof. |
| F | Evidence is insufficient to select A–E. |

These labels are future treatment hypotheses, not implementation approval.

## 3. Fixture class-to-defining-module map

The table contains the 21 explicit package-owned IDs in the inspected RA11A
attribution table. “Fixture role” deliberately remains `CANDIDATE` or
`UNKNOWN`; ordinary link reachability is not sufficient for global or
preprocessing packages.

| Class ID | Python class / defining module | Package entrypoint / registration | Aliases, generated IDs, or semantic notes | Fixture role |
|---|---|---|---|---|
| `Anything Everywhere` | `use_everywhere.py` (class definitions and IDs at `:7-151`) | `cg-use-everywhere/__init__.py:1-15`, V3 `comfy_entrypoint` | Sibling IDs include `Anything Everywhere3`, `Anything Everywhere?`, `Prompts Everywhere`, and other marker nodes. Frontend graph hooks are part of the semantic closure. | GLOBAL_SIDE_EFFECT_REQUIRED candidate; execution `UNKNOWN` |
| `CacheDiT_Model_Optimizer` | `ComfyUI-CacheDiT/nodes.py:839-1103` | `ComfyUI-CacheDiT/__init__.py:28-52` | Main NextDiT path; LTX2 and Wan mappings are eagerly imported siblings. | EXECUTION_REQUIRED candidate; exact branch `UNKNOWN` |
| `SystemNotification\|pysssss` | `comfyui-custom-scripts/py/system_notification.py:11,36-40` | `comfyui-custom-scripts/__init__.py:1-25` | Package entrypoint executes all top-level `py/*.py`; direct module import is not package-equivalent. | VALIDATION/EXECUTION candidate |
| `easy float` | `comfyui-easy-use/py/nodes/logic.py:1909` | `comfyui-easy-use/__init__.py:15-21` | Shared logic module also defines many unrelated IDs. | EXECUTION candidate |
| `easy globalSeed` | `comfyui-easy-use/py/nodes/seed.py:99,105` | Same package initializer | Easy-use server/global-seed behavior is separate metadata. | GLOBAL_SIDE_EFFECT/EXECUTION candidate |
| `easy ifElse` | `comfyui-easy-use/py/nodes/logic.py:1931` | Same package initializer | Shared broad logic module. | EXECUTION candidate |
| `easy imageSize` | `comfyui-easy-use/py/nodes/image.py` (fixture occurrence `clean_workflow.json:195,782`) | Same package initializer | Exact mapping line was not independently regenerated in this audit. | CANDIDATE; exact class mapping `SUPPORTED` |
| `easy indexAnything` | `comfyui-easy-use/py/nodes/logic.py:1943` | Same package initializer | Shared broad logic module. | EXECUTION candidate |
| `easy int` | `comfyui-easy-use/py/nodes/logic.py:1907` | Same package initializer | Shared broad logic module. | EXECUTION candidate |
| `easy showAnything` | `comfyui-easy-use/py/nodes/logic.py` (fixture `clean_workflow.json:31,102,115`) | Same package initializer | Exact mapping line not independently regenerated. | CANDIDATE; exact class mapping `SUPPORTED` |
| `easy stringToIntList` | `comfyui-easy-use/py/nodes/logic.py:1936` | Same package initializer | Shared broad logic module. | EXECUTION candidate |
| `ImpactIfNone` | `comfyui-impact-pack/modules/impact/logics.py:154` | `comfyui-impact-pack/__init__.py:64-256` | Broad Impact wildcard node loading and server import are separate closure items. | EXECUTION candidate |
| `ImpactSwitch` | `comfyui-impact-pack/__init__.py:64,202,397` (implementation in Impact logic family) | Same package initializer | Display mapping and broad explicit mapping must be preserved. | EXECUTION candidate |
| `JoinStrings` | `ComfyUI-KJNodes/nodes/nodes.py:255` | `ComfyUI-KJNodes/__init__.py:1-84,362-372` | KJ package also imports model/attention/media modules and installs a route. | EXECUTION candidate |
| `PathchSageAttentionKJ` | `ComfyUI-KJNodes/nodes/model_optimization_nodes.py:100` | KJ mapping generated at `__init__.py:88-370` | Spelling is the installed class ID. Optimization/global state must be tracked separately. | EXECUTION candidate; global hook `UNKNOWN` |
| `StringToCombo\|LP` | `comfyui-levelpixel/nodes/convert/convert_LP.py:118` | `comfyui-levelpixel/__init__.py:6-32` after `install_init.init()` | 17-module static `node_list`; import-time web/config bootstrap precedes mapping. | EXECUTION candidate |
| `SimpleMath+` | `comfyui_essentials/misc.py:9-80,232` | `comfyui_essentials/__init__.py:2-32` | Display alias `🔧 Simple Math` at `misc.py:242`; restricted AST evaluation occurs on execution. | EXECUTION candidate |
| `LayerUtility: PurgeVRAM V2` | `ComfyUI_LayerStyle/py/purge_vram.py:40,72-79` | `ComfyUI_LayerStyle/__init__.py:28-43` | Entry point imports all directly contained mapping-bearing `py/*.py` modules. | EXECUTION candidate |
| `LGNoiseInjectionLatent` | `comfyui_lg_samplingutils/py/noise_injection.py:213,395-402` | `comfyui_lg_samplingutils/__init__.py:2-47` | Package imports every child Python module; sibling modules are not proven required. | EXECUTION candidate |
| `ClownsharKSampler_Beta` | `RES4LYF/beta/samplers.py:1702` | `RES4LYF/__init__.py:1-60,391-463`, beta registration | Requires sampler/scheduler registration and order; `res_2s` implementation is in `beta/rk_coefficients_beta.py:60-62,1523-1560`. | EXECUTION_REQUIRED candidate; registration GLOBAL_SIDE_EFFECT_REQUIRED candidate |
| `Any Switch (rgthree)` | `rgthree-comfy/py/any_switch.py:14-38` | `rgthree-comfy/__init__.py:47-76` | Python selection is local, but package server/web context is broad. | EXECUTION candidate |
| `Image Comparer (rgthree)` | `rgthree-comfy/py/image_comparer.py:6-42` | rgthree package initializer | Saves A/B UI images; comparison presentation is frontend behavior. | VALIDATION/EXECUTION candidate |

### Upstream and non-package closure

The current fixture also references upstream/core or `comfy_extras` IDs,
including `CLIPLoader`, `UNETLoader`, `CLIPTextEncode`, `VAELoader`,
`VAEDecode`, `SaveImage`, `EmptyImage`, `EmptySD3LatentImage`,
`PrimitiveFloat`, `PrimitiveStringMultiline`, `ConditioningZeroOut`,
`ModelSamplingAuraFlow`, `ComfySwitchNode`, `CombineHooks8`, and
`CustomCombo`. `CustomCombo` is upstream `comfy_extras/nodes_logic.py`, not a
custom-node package. Core `nodes`, `folder_paths`, and `comfy.*` semantics are
not included in the 12-package count.

`ModelPatchLoader` is serialized in the current workflow but was identified by
RA11A as non-reachable; its presence in the persisted 61-entry file versus the
60-node runtime payload remains a documented discrepancy.

## 4. Registration mechanism table

| Package | Mechanism | Exact source evidence | Registration-only prerequisites | Package initialization before execution | Confidence / limitation |
|---|---|---|---|---|---|
| cg-use-everywhere | V3 async `comfy_entrypoint`, `ComfyExtension`; `WEB_DIRECTORY` | `__init__.py:1-15` | V3 entrypoint and frontend extension assets | Python marker classes plus frontend extension/graph hooks | PROVEN; browser callback order UNKNOWN |
| CacheDiT | V1 merged `NODE_CLASS_MAPPINGS` from three node modules | `__init__.py:28-52`; mappings `nodes.py:1097-1103`, `nodes_ltx2.py:818-825`, `nodes_wan.py:578-584` | Import mapping modules | Main optimizer class; selected model wrapper only on node use | PROVEN; optional `cache_dit` runtime behavior UNKNOWN |
| custom-scripts | V1 aggregate mappings, dynamic file-spec execution | `__init__.py:10-25` | `.pysssss.init()` and every top-level `py/*.py` execution | All 14 child modules are currently executed by normal package init | PROVEN; filesystem ordering and failure behavior remain dynamic |
| easy-use | V1 aggregate mappings from 15 eagerly imported node modules | `__init__.py:15-24` | Routes/server/wildcard/config and prestartup path setup | All selected node modules plus broad package setup | PROVEN; exact per-node bundled model closure UNKNOWN |
| Impact | V1 explicit broad mapping plus wildcard node imports | `__init__.py:45-56,64-295` | Config, server import, wildcard loader startup | Broad node modules, route API, frontend alias, wildcard thread | PROVEN |
| KJNodes | V1 generated mapping from explicit imports and `NODE_CONFIG` | `__init__.py:1-84,88-372` | Explicit import list and mapping generation; optional LTXV | Broad media/model/optimization imports and `/kjweb_async` route | PROVEN; optional LTXV success UNKNOWN |
| LevelPixel | V1 merged mappings from static 17-module list | `__init__.py:6-32` | `install_init.init()` before mappings | Config and web bootstrap plus all listed node modules | PROVEN; configured target path UNKNOWN |
| essentials | V1 merged category mappings from seven modules | `__init__.py:2-32` | Seven category modules | All category imports; deferred feature modules only on use | PROVEN |
| LayerStyle | V1 merged mappings from every direct `py/*.py` import | `__init__.py:28-43` | Directory enumeration and permissive per-module import handling | All 133 mapping-bearing modules attempted | PROVEN; failed-module set UNKNOWN |
| lg_samplingutils | V1 merged mappings from every child `py/*.py` import | `__init__.py:2-47` | Directory enumeration | Four child modules imported | PROVEN |
| RES4LYF | V1 mapping plus dynamic beta/legacy/Zampler registration | `__init__.py:1-60,391-463`; `res4lyf.py:100-116` | Global sampler/scheduler tables and reload order | Broad base modules plus registration side effects | PROVEN; optional imports environment-dependent |
| rgthree-comfy | V1 mapping plus config-gated Dynamic Context and server routes | `__init__.py:15-79`; `py/server/rgthree_server.py:1-28` | Node imports, PromptServer route installation, web resources | Broad node/server imports; config decides some IDs | PROVEN; frontend load order UNKNOWN |

Current ComfyUI discovery executes a directory package initializer under a
synthesized module name, then handles V1 mappings or V3 entrypoints:
`ComfyUI/nodes.py:2192-2323`. A class allowlist therefore does not recursively
restrict what an allowed package’s initializer imports.

## 5. Package-by-package import amplification and side effects

The following table is the primary reusable metadata inventory. “Imported at
entrypoint” means source-proven package behavior, not a runtime observation.

| Package | Static Python count / entrypoint import amplification | IMPORT-TIME | FIRST-USE / EXECUTION-TIME | Third-party/native and global state | Narrowing classification |
|---|---|---|---|---|---|
| **cg-use-everywhere** | 3 Python modules; approximately 15 frontend JS modules in the effective web surface. Python entrypoint is narrow; frontend surface is intentionally graph-wide. | Imports `use_everywhere`; exposes `./js`; frontend `app.registerExtension()` and hooks. | Frontend graph conversion, implicit connection repair, nested-subgraph traversal, queue/prompt transformation, and graph lifecycle mutation. Python marker `execute()` methods are mostly no-ops. | Frontend graph-global state (`shared.py:5-12`); no Python thread/installer/network proven. | **E** — frontend/global semantics cannot be replaced by ordinary linked-node reachability. |
| **ComfyUI-CacheDiT** | 5 Python source modules; all three node modules imported by `__init__`, including LTX2 and Wan siblings. | Imports Torch, Comfy patcher/extension APIs, logging/config helpers; merges all three mappings. | `nodes.py:625-697` enables the lightweight NextDiT path; wrappers, forward replacement, cache state, model options, and optional `cache_dit` occur on use. | Per-transformer/module-global cache state (`nodes.py:43-54`); `OUTER_SAMPLE`/`DIFFUSION_MODEL` wrappers; no package thread/route/file write proven. | **C** — main class-specific module seam is plausible, but wrapper ordering and optional backend need parity proof. |
| **comfyui-custom-scripts** | 16 Python files total; `__init__.py` dynamically executes all 14 top-level `py/*.py` modules after importing `pysssss`. | `pysssss` imports `aiohttp`, PromptServer, tqdm and async/filesystem helpers; autocomplete, combo, and model-info routes register; autocomplete creates the user directory/file. | Metadata hashing/sidecar writes (`py/model_info.py:98-112`), example resources, and individual node operations. | Heavy optional imports include Torch/PIL/NumPy in child modules; routes and user files; no package-local model installer proven. | **C** — direct class/module seam plausible only with explicit shared initializer/route policy; normal entrypoint is broad. |
| **comfyui-easy-use** | 99 Python files; 15 node modules plus routes/server/wildcard support are eagerly imported. | `__init__.py:26-90` creates wildcard/styles resources and may rewrite `config.yaml`; `prestartup_script.py:3-34` mutates `folder_paths`; routes and global prompt handler install. | Route model/cache/style operations; selected loader, sampler, adapter, API, and bundled model families execute on use. | Broad Torch/Comfy/model families; global model path registry, PromptServer handler, frontend selection, config/resources. | **E** — initializer and global model-path/prompt semantics are too deep for unproven class-only bypass. |
| **comfyui-impact-pack** | 31 Python files; imports config/server and 11 wildcard node modules, plus explicit broad mapping. | Torch/OpenCV/NumPy/PIL/skimage/piexif imports; Impact server import; JS extension directory injection; starts non-daemon wildcard loader thread at `__init__.py:58-61`. | Wildcard resource scan/load; detector/SAM/HF/detailer/sampler model operations. `install.py` contains model download/subprocess logic but is not imported by `__init__.py`. | Background thread, PromptServer/API registration, `nodes.EXTENSION_WEB_DIRS`, mutable resource state; installer risk is separate and not proven on normal import. | **D** — a package-aware bootstrap may be possible, but thread/server/wildcard parity is mandatory. |
| **ComfyUI-KJNodes** | 19 Python files; 18 direct module imports plus optional LTXV attempt; one broad generated mapping. | Explicit Torch/Comfy/PIL/OpenCV/audio/video/optimization imports; optional LTXV; `/kjweb_async` route registration. | Advanced-ControlNet import on use (`model_optimization_nodes.py:2077`), optional pandas/librosa, preview transport, Torch Dynamo mutation. | PromptServer route, optional integration state, model/attention/compiler behavior; duplicate/overwritten mapping names are order-sensitive. | **D** — explicit package-specific bootstrap might preserve route and mapping semantics; class-only bypass is unproven. |
| **comfyui-levelpixel** | 18 Python files; 17 static node-list modules imported after bootstrap. | `install_init.init()` may create config, unlink/delete/copy/link web tree (`install_init.py:56-159`); tag JSON read; heavy Torch/SciPy/TorchVision/PIL imports. | Image processing; `model_unloaders_LP.py:162-163` performs an outbound `requests.post`; model/device actions depend on node use. | Import-time filesystem mutation and config creation; network is execution-time in inspected source; no installer execution performed. | **E** — normal init is mutation-prone; no safe class-specific treatment without package-aware upstream change. |
| **comfyui_essentials** | 11 Python source modules; seven category modules eagerly imported and two feature modules deferred. | Imports Torch/NumPy/SciPy/TorchVision/Kornia/Numba/PIL and Comfy internals through category modules; computes font/LUT paths. No routes/threads/writes found. | Deferred seam carving, histogram matching, rembg, transparent-background, pixeloe, colour, and Transformers CLIPSeg; `from_pretrained` may use network/cache; GPU/model work and `torch.compile` on use. | Large native/third-party import surface but no package-global hooks proven; font/LUT enumeration occurs through `INPUT_TYPES()`. | **C** — `misc.py` seam for `SimpleMath+` is plausible; category registration and dependency parity required. |
| **ComfyUI_LayerStyle** | 140 Python files; 133 mapping-bearing `py/*.py` modules are attempted by entrypoint. | `os.listdir(py)` and import-all at `__init__.py:28-43`; most modules import Torch/PIL/NumPy/SciPy/OpenCV/shared `imagefunc`; failures are silently skipped; `WEB_DIRECTORY` exposed. | Layer/image processing, segmentation, background removal, model inference, and file operations. | Heavy BRIA/segformer modules are imported even when unused; no server route or thread proven in entrypoint; skipped-module registry is not retained. | **C** — direct module seam is plausible because no package-global hook was proven, but mapping/failure parity is required. |
| **comfyui_lg_samplingutils** | 5 Python source modules; four child modules imported via `os.listdir`/`importlib`. | Dynamic child import and mapping merge; no installer/network/thread/route/global sampler mutation found. | `sampling_offset.py:57-65` performs per-model `add_object_patch`; other child node behavior runs on use. | Per-model patch state, not global sampler registry; dynamic import order and suppressed mapping-serialization errors remain. | **C** — clean child-module seam is plausible; package registration and sibling failure behavior need proof. |
| **RES4LYF** | Exact total not re-counted in this audit; broad base modules plus optional beta/legacy/Zampler surfaces are eagerly/conditionally loaded. | Registers `bong_tangent`; `res4lyf.init()` mutates scheduler names/tables; `add_samplers()` mutates `KSampler.SAMPLERS`, attaches functions, and reloads `k_diffusion_sampling` (`__init__.py:20-25,40-60`; `res4lyf.py:100-116`). | `res_2s` and sibling algorithms in `beta/rk_coefficients_beta.py`; beta sampler/unsampling machinery calls Comfy sampling. | Process-global sampler/scheduler tables, attached functions, `extra_options`, import-order/reload effects; optional imports catch failures inconsistently. | **E** — sampler registration is semantic global state; direct class import is not equivalent. |
| **rgthree-comfy** | Approximately 25 local Python node/server modules eagerly imported; approximately 50 frontend JS modules are present. | Node mappings, route modules, static routes, config; deletes legacy web-extension directories (`__init__.py:85-92`); PromptServer routes install. | Any Switch, Dynamic Context, Image Comparer, model-info refresh/clear; CivitAI request/cache via `utils_info.py:328-349`; frontend graph/context behavior. | Global route registry, web resources, config state, model-info disk caches, optional network; no explicit thread/executor/timer proven. | **E** — server/web and graph-context semantics require package-aware proof; no blanket class-only import. |

### Broad behavior count

For the completion fields, **high import amplification** means a package entry
point eagerly imports a materially broad sibling surface or performs broad
initialization unrelated to one class, not that every imported module is
unnecessary for every workflow. By that definition the count is 8:

`comfyui-custom-scripts`, `comfyui-easy-use`, `comfyui-impact-pack`,
`ComfyUI-KJNodes`, `comfyui-levelpixel`, `ComfyUI_LayerStyle`, `RES4LYF`, and
`rgthree-comfy`.

## 6. Import-time resource and mutation inventory

| Package | Filesystem reads | Filesystem writes/deletes | Network | Routes/web | Global state/resources | Phase and confidence |
|---|---|---|---|---|---|---|
| cg-use-everywhere | Frontend graph/settings reads are host/browser dependent | Frontend graph/link state mutation | None proven | `WEB_DIRECTORY`; frontend extension | Graph callbacks, implicit links, prompt transformation flags | IMPORT-TIME registration; FIRST-USE/EXECUTION graph behavior PROVEN/SUPPORTED |
| CacheDiT | Source/module imports; no package resource scan proven | None proven at entrypoint | None proven | None proven | Mappings; later model options/forward/wrapper state | IMPORT-TIME / FIRST-USE split PROVEN |
| custom-scripts | Module files; model-info route reads | Autocomplete user path and route metadata/example sidecars | None proven | Autocomplete, combo, model-info routes | PromptServer route registry | Routes IMPORT-TIME; model writes FIRST-USE |
| easy-use | Config, wildcard/style resources, model-path setup | Wildcard/style example creation; possible `config.yaml` rewrite | Route/network behavior not proven at import | Many `/easyuse/*` routes; prompt handler; frontend choice | `folder_paths`, server global seed, config | IMPORT-TIME mutation PROVEN; route work FIRST-USE |
| Impact | Config and wildcard/resource scan | Wildcard/resource behavior; installer source has download path but is not imported | Installer/download path separate; normal init not proven to call it | Impact server; JS extension dir | Non-daemon wildcard thread | IMPORT-TIME background resource risk PROVEN; installer risk SUPPORTED separate |
| KJNodes | Module imports and optional integration checks | None proven | None proven | `/kjweb_async`, preview/websocket path | Mapping collisions, PromptServer, execution-time Torch Dynamo | IMPORT-TIME route; FIRST-USE optional imports |
| LevelPixel | `levelpixel.json`, tag JSON, source/web trees | Config creation; unlink/delete/link/copy web extension | `requests.post` in unloader execution | PromptServer imported by bootstrap | Web tree/config state | IMPORT-TIME filesystem mutation PROVEN; network EXECUTION-TIME |
| essentials | Font/LUT paths; category imports | None proven | Transformers model access possible on CLIPSeg use | None proven | No package-global registry/hook proven | IMPORT-TIME imports; FIRST-USE resource/model behavior |
| LayerStyle | `os.listdir(py)` and module imports | No entrypoint write proven | None proven | `WEB_DIRECTORY` | Mapping registry; failed imports silently omitted | IMPORT-TIME import-all PROVEN |
| lg samplingutils | `os.listdir(py)` and module imports | None proven | None proven | None proven | Mapping registry; per-model patch on use | IMPORT-TIME import-all; EXECUTION-TIME model patch |
| RES4LYF | Optional marker/package checks | No installer/write proven in normal init | None proven | None proven | Sampler/scheduler global mutation and reload | IMPORT-TIME semantic mutation PROVEN |
| rgthree-comfy | Config/web/module imports; model-info cache on route use | Deletes old web directories at import; cache writes on route use | CivitAI `requests.get` on model-info route | PromptServer/static/model routes | Route registry, config, caches | IMPORT-TIME deletion/routes; FIRST-USE network/cache |

### Background resources

One package has a source-proven import-time background resource: Impact starts a
non-daemon wildcard-loading thread. No explicit import-time thread, executor,
timer, socket, or long-lived file descriptor was proven for the other 11
packages. This is not proof that dependencies cannot create resources.

## 7. Safe/unsafe narrowing assessment

| Package | Best plausible generic treatment | Why | Conditions before any experiment |
|---|---|---|---|
| cg-use-everywhere | **E** | Python classes are markers; frontend graph-wide behavior is the actual semantic payload. | Preserve extension registration, nested subgraphs, implicit links, prompt rewrite, and frontend lifecycle. |
| CacheDiT | **C** | Main and model-family modules are separable in source; main path has explicit wrapper seam. | Prove wrapper ordering, disable/restore, optional backend, model switching, and all mappings. |
| custom-scripts | **C** | `system_notification.py` can be identified, but `pysssss` and package aggregation are required metadata. | Compare routes, mapping/display maps, shared initializer, file effects, and all generic workflows. |
| easy-use | **E** | Prestartup model paths, prompt handler, routes, config, and resources are package-global. | Only package-aware selective bootstrap after proving global hooks and model-path closure. |
| Impact | **D** | Broad imports and wildcard thread/server are substantial but potentially explicit. | Reproduce wildcard/resource readiness, API, frontend alias, and shutdown/quiescence. |
| KJNodes | **D** | Explicit imports make a package bootstrap conceivable; route and optional integrations are global. | Preserve mapping generation, collision order, LTXV policy, route, and execution-time integrations. |
| LevelPixel | **E** | Import itself can mutate/delete/link the web tree and create config. | Upstream/package change or a proven no-mutation initializer; do not bypass by direct import alone. |
| essentials | **C** | Category modules are explicit; `SimpleMath+` is in `misc.py`; no package-global hook proven. | Preserve mapping/display/schema output and dependency behavior for later workflows. |
| LayerStyle | **C** | No package-global route/hook proven; direct mapping module is identifiable. | Preserve shared `imagefunc`, mapping aggregation, import failure semantics, and future IDs. |
| lg samplingutils | **C** | Four child modules and per-model patching are explicit; no global sampler registration found. | Prove all child mappings, package ordering, and `add_object_patch` behavior. |
| RES4LYF | **E** | Sampler/scheduler registration and reload are process-global correctness state. | Reproduce exact registration order or retain complete package initializer. |
| rgthree-comfy | **E** | Routes, web deletion, model-info cache/network, and context semantics exceed class lookup. | Preserve server/web/context services; do not import only the two Python classes. |

No package is classified `A` on the available evidence. `F` is not selected as
the primary treatment for a package because each package has enough source
evidence for a bounded risk classification, although every package retains
some unresolved runtime behavior.

## 8. Generic workflow-driven initialization model

The future resolver must join RA11C semantic closure to this package metadata,
not hardcode the current fixture:

```text
WORKFLOW_RUNTIME_CLOSURE
  class IDs + node IDs + subgraphs + aliases/generated IDs
  V1/V3/legacy registration requirements
  registration-only and validation-only requirements
  graph-global providers/hooks and preprocessing rewrites
  selected dynamic/lazy branches
  package initializer/import/global-hook/preprocessing dependencies

INSTALLED/PUBLISHED ENVIRONMENT
  complete package trees and dependency environment available to all workflows

PROCESS_INITIALIZED_SET
  already initialized package/initializer/global-hook identities in this process
  sticky partial-failure records; no unload
```

### Required metadata for a reusable package record

Each package/initializer record should eventually carry:

- stable package ID, repository/revision/source identity, and root-relative
  logical path (never an absolute Windows path as semantic identity);
- V1/V3/legacy registration kind, entrypoint, sync/async behavior, schema and
  `NodeOutput` normalization where applicable;
- owned class IDs, Python qualified names, aliases/generated IDs, display maps,
  `RELATIVE_PYTHON_MODULE`, collision/order behavior, and dynamic IDs;
- initializer ID, prerequisites, ordering constraints, idempotence/reentrancy,
  registration outputs, global hooks, web/routes, preprocessing, and resources;
- direct and transitive imports, dynamic enumeration rules, optional branches,
  heavyweight/native imports, and unresolved paths;
- `safe_to_lazy_initialize = proven | unknown | unsafe`;
- side-effect/resource declarations: files, routes, model paths, registries,
  sampler/scheduler mutation, monkeypatches, attention hooks, threads,
  executors, timers, file descriptors, caches, network, installers, and
  subprocesses;
- proof level per field and source references; and
- `required_by` edges distinguishing class registration, validation,
  preprocessing, global semantics, and execution.

### Proof levels

| Level | Meaning | Resolver consequence |
|---|---|---|
| P0 | Unknown, dynamic, failed, or unmeasured | Cannot authorize selective initialization. |
| P1 | Installed identity/inventory only | Establishes provenance, not importability or safety. |
| P2 | Registration mapping/schema observed | Establishes class presence, not closure or execution correctness. |
| P3 | Initializer, imports, globals, preprocessing, ordering, and dynamic paths bounded | Minimum level to authorize workflow-derived initialization. |
| P4 | Workflow behavior/output/durability parity observed | Required for execution/parity claims, not merely class ownership. |

### Monotonic process rules

1. Derive `required_closure - process_initialized_set`.
2. Serialize initialization per process; never duplicate V1/V3 registration
   concurrently.
3. Add an initializer to the proven initialized set only after its required
   registration/global checks succeed.
4. Keep partial-failure state separately. Do not represent a package that
   mutated state and then failed as cleanly uninitialized.
5. Never unload modules, unregister mappings, undo hooks, or reload a different
   package revision in a live process.
6. If the resolver cannot establish P3, choose the existing complete discovery
   path before speculative selective initialization. “Complete discovery” means
   the standard broad attempt, not a guarantee that every package succeeded.
7. If the required class/global behavior is still absent after complete
   discovery, fail closed.

This is the generic architecture for Golden and non-Golden workflows. Golden’s
current class/module table is fixture evidence used to test the resolver, not a
permanent allowlist.

## 9. Snapshot implications

Selective initialization changes the Python/native object graph present at CPU
snapshot capture. A future experiment must record, per process and initializer:

- threads and thread liveness, including Impact’s wildcard loader;
- executors, futures, timers, and pending background work;
- open files/sockets and route/server objects;
- mutable registries and package-global caches;
- model paths and filesystem/config state;
- native library/allocator state and package-created model/session objects; and
- sticky partial-failure or optional-import state.

The snapshot must be quiescent before capture. No QD owner, open checkpoint
reader, request worker/future, model payload, or package background activity may
be retained unless explicitly part of the generic snapshot contract. Lower
logical module count or lower observed snapshot RSS is not evidence of lower
restore or E2E latency, and this audit provides no such measurement.

## 10. S4 publication/runtime-closure separation

Runtime package closure is independent of S4 publication semantic content.

```text
WORKFLOW_RUNTIME_CLOSURE != S4_PUBLICATION_SEMANTIC_CONTENT_CLOSURE
```

A future resolver may initialize fewer packages for one workflow, but it must
not shrink, reinterpret, or optimize the S4 semantic publication set merely
because those packages were not needed by that request. The complete installed
and published environment remains available to later workflows. S4 publication
correctness, full-content generation, receipt identity, and Volume authority
remain governed by their existing contracts.

## 11. Parity tests required before any generic narrowing

Any future implementation must test the generic mechanism in isolated
processes, first with the Golden fixture and then with non-Golden workflows:

1. **Discovery parity:** same V1 mappings, V3 node lists/schemas, display maps,
   relative module metadata, aliases, generated IDs, collision order, and
   import failures as complete discovery.
2. **Initializer parity:** exact initializer ordering, prerequisites,
   idempotence, re-entry, optional branches, and partial-failure records.
3. **Global parity:** sampler/scheduler tables, attention/model hooks,
   PromptServer routes, model paths, frontend extension directories, graph
   preprocessing, nested subgraphs, and prompt transformation.
4. **Registration/execution separation:** prove registration-only,
   validation-only, global-side-effect, and executed classes independently;
   do not use class presence as execution evidence.
5. **Dynamic behavior:** aliases, generated classes, V3 async entrypoints,
   lazy imports, optional dependencies, unknown branch selection, and package
   import-all behavior must either be proven or trigger complete discovery.
6. **Monotonic multi-workflow sequence:** workflow A initializes a subset,
   workflow B adds packages, workflow A/B repeat, and no prior registration is
   lost or duplicated.
7. **Fallback correctness:** unknown/unsafe closure selects complete discovery
   before selective side effects; missing required classes/global state fail
   closed.
8. **Non-Golden regression:** workflows using packages/classes absent from the
   fixture, including future V1/V3 and graph-global workflows, retain behavior.
9. **Resource/quiescence:** compare threads, executors, timers, FDs, caches,
   routes, model paths, filesystem state, and snapshot capture state.
10. **Actual endpoint parity:** valid workflows preserve output semantics,
    exactness where contracted, durability ordering, and result delivery. Do
    not substitute import counts for runtime evidence.
11. **S4 isolation:** package filtering leaves publication content identity and
    semantic publication scope unchanged.
12. **RA11E interaction:** deep profiling/diagnostic flags are behavior gates,
    not proofs that legacy/comfymodal imports are absent; preserve generic
    workflows when cleaning universally avoidable imports.

## 12. Reconciliation inputs

### RA11C should join to this report

- exact serialized/runtime workflow hashes and rewrite/omission map;
- per-node ID, class, parent/subgraph, semantic role, and selected branch;
- executed, seeded, validation-only, registration-only, global, UI,
  unreachable, and unknown classifications;
- observed preprocessing and execution events;
- package/class attribution with fixture-only confidence; and
- any dynamic class, alias, V3, or graph-global evidence.

### RA11E should join to this report

- configuration and diagnostic flags;
- imported-module reachability and universally avoidable versus workflow-valid
  imports;
- wrapper-install attempts and legacy-runtime bridges;
- deep-profile and stage-diagnostic state; and
- evidence that import cleanup remains generic and does not remove capabilities
  needed by other workflows.

The eventual decision is therefore:

```text
RA11C semantic workflow closure
  + RA11D initializer/import/global side-effect metadata
  + RA11E generic comfy-modal import amplification
  -> smallest safe generic lazy-initialization experiment
```

## 13. Exact source evidence index

### Host discovery and Golden

- `ComfyUI/nodes.py:2192-2323` — directory package loading, V1 mappings,
  V3 `comfy_entrypoint`, `on_load`, `get_node_list`, and top-level discovery.
- `comfymodal_runtime/golden_serial.py:1-35` — documented Golden module
  boundary and no normal PromptExecutor execution.
- `comfymodal_runtime/golden_serial.py:3595-3656,3822-3889` — node-map
  resolution and Golden execution entrypoint.
- `comfymodal_runtime/golden_serial.py:6120-6331,6811-6822` — selected output
  handling and serial stage order.
- `clean_workflow.json:6-836` — pinned workflow serialization.
- `.studio_custom_nodes.json:1-1843` — installed attribution artifact.
- `RA11A_MINIMAL_GOLDEN_RUNTIME_DEPENDENCY_CLOSURE_REPORT.md:61-85,169-235`
  — fixture attribution and current discovery/closure context.
- `RV2B_REMOTE_GOLDEN_BASELINE_TRUTH_REPORT.md:23-106,348-397` — current
  remote identity and baseline limitations; no import-narrowing evidence.

### Package evidence

- `cg-use-everywhere/__init__.py:1-15`, `use_everywhere.py:7-151`,
  `js/use_everywhere.js:68-228`, `js/connections.js:31-131`,
  `js/recursive_callbacks.js:6-63`, `shared.py:5-12`.
- `ComfyUI-CacheDiT/__init__.py:28-52`, `nodes.py:43-54,215-289,625-826,
  839-1103`, `nodes_ltx2.py:595-825`, `nodes_wan.py:447-584`,
  `utils.py:252-303,394-410,683-696`.
- `comfyui-custom-scripts/__init__.py:1-25`, `pysssss.py:1-44`,
  `py/autocomplete.py:1-29`, `py/better_combos.py:1-164`,
  `py/model_info.py:1-112`, `py/system_notification.py:11,36-40`.
- `comfyui-easy-use/__init__.py:1-95`, `prestartup_script.py:1-34`,
  `py/routes.py:1-206+`, `py/server.py:1-166`, `py/config.py:1-386`.
- `comfyui-impact-pack/__init__.py:8-61,64-295,449-454`,
  `modules/impact/impact_server.py`, `modules/impact/wildcards.py`,
  `install.py:1-106` (separate installer path, not normal entrypoint import).
- `ComfyUI-KJNodes/__init__.py:1-390`, `nodes/model_optimization_nodes.py:1-1322+,
  2077`, `nodes/preview_override_node.py:26-610`.
- `comfyui-levelpixel/__init__.py:1-35`, `install_init.py:1-159`,
  `nodes/image/image_utils_LP.py:1-584`,
  `nodes/image/inpaint_crop_stitch_LP.py:1-1023`,
  `nodes/unloaders/model_unloaders_LP.py:1-176`,
  `nodes/convert/convert_LP.py:118`, `nodes/tags/tags_utils_LP.py:1-662`.
- `comfyui_essentials/__init__.py:2-32`, `misc.py:9-80,232-242`,
  `image.py:27-1610,1613-1697`, `segmentation.py:6-79`, `utils.py:1-43`,
  `requirements.txt:1-5`.
- `ComfyUI_LayerStyle/__init__.py:1-48`, `py/purge_vram.py:40,72-79`,
  `py/briarmbg.py:1-347`, `py/segformer_ultra.py:1-923`.
- `comfyui_lg_samplingutils/__init__.py:2-47`,
  `py/sampling_offset.py:10-81`, `py/noise_injection.py:213,395-402`.
- `RES4LYF/__init__.py:1-60,391-463`, `res4lyf.py:100-116`,
  `beta/rk_coefficients_beta.py:60-62,1523-1560`,
  `beta/samplers.py:183-327,625-716,1011-1071,1702`.
- `rgthree-comfy/__init__.py:15-126`, `py/server/rgthree_server.py:1-28`,
  `py/server/routes_config.py:1-64`, `py/server/routes_model_info.py:1-152`,
  `py/server/utils_info.py:7,328-349`, `py/any_switch.py:14-38`,
  `py/image_comparer.py:6-42`, `py/dynamic_context.py:7-56`.

## 14. Completion fields

Counts use the definitions stated in this report. “Dynamic import package”
counts entrypoint child enumeration/import behavior or RES4LYF’s conditional
registration import surface; frontend module loading alone is not counted.
“Background resource package” counts source-proven package-entrypoint-created
threads/executors/timers, not later route/model work.

```text
RA11D_COMPLETE=YES
PACKAGES_AUDITED=12
GOLDEN_ATTRIBUTED_CLASSES_TRACED=21
DYNAMIC_IMPORT_PACKAGES=5
HIGH_IMPORT_AMPLIFICATION_PACKAGES=8
BACKGROUND_RESOURCE_PACKAGES=1
INSTALL_OR_SOURCE_MUTATION_RISKS=4
CLEAN_CLASS_SPECIFIC_IMPORT_SEAMS=3
PACKAGE_SHIM_CANDIDATES=2
UNSAFE_TO_NARROW=5
UNRESOLVED_PACKAGES=12
S4_PUBLICATION_SCOPE_UNCHANGED=YES
RUNTIME_MODEL=ONE_GENERIC_WORKFLOW_DRIVEN_RUNTIME
GOLDEN_ROLE=FIXTURE_ONLY
INSTALLED_ENVIRONMENT=COMPLETE
PROCESS_INITIALIZATION=MONOTONIC_ADD_ONLY
UNPROVEN_CLOSURE_FALLBACK=COMPLETE_DISCOVERY
PACKAGE_FACTS=FIXTURE_OR_AUDIT_EVIDENCE_ONLY
RUNTIME_SOURCE_MODIFIED=NO
CUSTOM_NODE_SOURCE_MODIFIED=NO
MODAL_CONTACTED=NO
COMMITS_CREATED=NO
REPORT=RA11D_CUSTOM_NODE_INTERNAL_CLOSURE_AND_SIDE_EFFECT_AUDIT.md
```

Count notes:

- `DYNAMIC_IMPORT_PACKAGES=5`: custom-scripts, LevelPixel, LayerStyle,
  `comfyui_lg_samplingutils`, and RES4LYF’s conditional optional registration
  surface. Impact/KJ wildcard/explicit imports are broad but not counted as
  child-enumeration packages in this field.
- `INSTALL_OR_SOURCE_MUTATION_RISKS=4`: custom-scripts, easy-use, LevelPixel,
  and rgthree have source-proven normal-entrypoint filesystem/config mutation
  or deletion risk. Impact’s separate `install.py` is not counted because the
  normal entrypoint does not import it.
- `CLEAN_CLASS_SPECIFIC_IMPORT_SEAMS=3`: CacheDiT, `comfyui_essentials`, and
  `comfyui_lg_samplingutils` have the clearest source-level seams; custom-scripts
  remains a conditional seam candidate but its shared initializer/routes make
  safety unproven.
- `PACKAGE_SHIM_CANDIDATES=2`: Impact and KJNodes have substantial but explicit
  package bootstrap state that may be reproducible with package-aware metadata;
  this is not implementation approval.
- `UNSAFE_TO_NARROW=5`: cg-use-everywhere, easy-use, LevelPixel, RES4LYF, and
  rgthree have correctness-sensitive package-global behavior on current source
  evidence.
- `UNRESOLVED_PACKAGES=12`: every audited package retains at least one material
  dynamic, environment-dependent, unexecuted, or dependency-internal question.
