# RA11C — Exact Workflow Execution Closure Audit (Golden Fixture)

**Date:** 2026-08-30  
**Scope:** read-only reconciliation of the pinned workflow, the current Golden
benchmark/reference fixture, and retained RV2B execution evidence. Golden is
only the fixture used for this benchmark; it is not a special runtime or a
separate architecture. No runtime, configuration, or source file was modified.
No Modal operation was performed.

## Decision

The serialized/runtime count discrepancy is resolved from the retained runtime
payload, not from JSON presence alone:

* `clean_workflow.json` contains 61 entries.
* `latest_benchmark_workflow.json` retains the exact Golden request payload and
  contains 60 entries.
* The only serialized key absent from that request payload is `1501`, whose
  class is `ComfySwitchNode`.
* The request payload also records the corresponding semantic rewrite:
  `1262 / LGNoiseInjectionLatent.inputs.model` points directly to `1499 /
  PathchSageAttentionKJ`, rather than to `1501`.
* `151 / ModelPatchLoader` is present in the 60-node request payload, but has no
  links or consumers and is not executed. It is not the count discrepancy.

The strongest RV2B evidence is the repeated `output_branch_executed` event and
the sampler-preparation `executed_nodes` list. The same 32-node execution set
is retained across the five eligible requests. The event list is treated as
authoritative over static graph inference.

The observed fixture closure is **not** a hardcoded runtime allowlist. The node
semantics are classified, but package `__init__` amplification, package side
effects, registration order, and exact transitive import closure still require
an isolated parity experiment. The observations below should seed reusable
workflow/package metadata; they must not become Golden-specific runtime logic,
permanent Golden-only initialization, package deletion, or an `if golden_p1`
branch.

## Generic workflow-driven closure model

The reusable runtime contract is driven by the incoming workflow, not by the
name of this fixture or by a benchmark phase:

```text
incoming workflow
  -> determine class semantics
  -> derive custom-node/package/global-initializer closure
  -> initialize only requirements not already available
  -> validate
  -> execute
```

Keep these three sets explicitly separate:

* **WORKFLOW_RUNTIME_CLOSURE** — the classes, packages, registrations,
  preprocessors, hooks, and other requirements proven relevant to this
  workflow and its selected execution/output contract.
* **INSTALLED/PUBLISHED_ENVIRONMENT** — the complete installed and published
  package environment. It remains complete; a workflow closure is not a reason
  to delete, omit, or unpublish packages.
* **PROCESS_INITIALIZED_SET** — requirements successfully initialized in the
  current process. This set is monotonic: initialization may add entries, but
  never unload registrations or remove entries from the set.

For each workflow, initialization is the difference between the derived
closure and the requirements already available in the process. Validate the
resulting mappings, hooks, schemas, preprocessing, and resource contracts
before execution. When a closure is proven safe and stable, it may be cached
by workflow/content identity (including the relevant workflow and package
metadata); cache hits must still respect the installed/published environment
and the monotonic process-initialized set. If the closure cannot be proven,
complete the existing broad discovery fallback rather than guessing a
filtered set.

The closure derivation must account for more than ordinary links. Graph-global
nodes and hooks, registration-only classes, sampler/scheduler registrations,
package import side effects, and preprocessing may be required even when no
individual node is executed. Generated or aliased IDs must be resolved without
assuming numeric identity. V1 and V3 registration/normalization paths must
both be covered. Dynamic/lazy nodes must be expanded or queried as required by
the workflow, while preserving lazy branch semantics. None of these facts
turns the Golden fixture into a special runtime.

## Evidence inventory

| Evidence | Finding |
|---|---|
| `clean_workflow.json` | 61 serialized mapping entries; includes `1501 / ComfySwitchNode`. |
| `latest_benchmark_workflow.json` → `payload.prompt` | 60-node request payload; excludes `1501`; changes `1262.model` to `1499`. The payload canonical hash is the RV2B hash `e44389ea...`. |
| `RV2B_REMOTE_GOLDEN_BASELINE_RAW_LOG.md:28898-28924` | 26-node sampler-preparation execution list. |
| `RV2B_REMOTE_GOLDEN_BASELINE_RAW_LOG.md:39245-39248` | 3-node CLIP-forward execution list. |
| `RV2B_REMOTE_GOLDEN_BASELINE_RAW_LOG.md:39408-39448` | Complete 32-node output-branch execution list and `SaveImage`/`Any Switch` evidence. |
| `RV2B_REMOTE_GOLDEN_BASELINE_TRUTH_REPORT.md:81-87` | Five valid, true-cold, durable RV2B requests; output SHA warning is unrelated to node closure. |
| `golden_serial.py:3150-3168` | Runner executes dependency closures serially; seeded nodes are never executed. |
| `golden_serial.py:3400-3557` | Class lookup, lazy dependency handling, direct V1 function calls, V3 normalization, and closure traversal. |
| `golden_serial.py:4622-4759,5374-5436,6022-6049,6120-6215` | Exact stage closures, seeded heavy nodes, decode, selected output branch, and deliberate SaveImage bypass. |
| `golden_serial.py:6764-6827` | Authoritative stage order from restore observation through durability. |
| `modal_app.py:21110-21215,21290-21308` | Golden receives the installed `nodes.NODE_CLASS_MAPPINGS` and calls `golden_serial_execute` once. |

## Observed Golden fixture path

The current benchmark/reference fixture path is:

```text
REAL RESTORE observation
  -> golden_request_setup / hash / canonical node map / model paths
  -> CLIP load
  -> CLIPTextEncode dependency closure
  -> UNET load
  -> sampler dependency closure, stopping before sampler
  -> VAE load
  -> ClownsharKSampler_Beta closure and sampling
  -> sampler tail bookkeeping
  -> VAEDecode closure
  -> selected Any Switch (rgthree) output branch
  -> SaveImage-compatible PNG encoding without executing SaveImage
  -> Volume commit / reopen / stat / read / hash
  -> teardown and telemetry persistence
```

The fixture's `resolve_golden_node_map` (`golden_serial.py:3595-3656`) resolves
only the six canonical heavy identities. This is an observation of the
reference implementation, not a generic runtime rule, and does not imply
that every prompt entry is executed. The fixture's `GoldenSerialRunner._ensure`
skips links declared lazy by the node schema; `_execute_one` invokes
`check_lazy_status`, then calls the declared V1 `FUNCTION` directly. V3
`NodeOutput` values are narrowly normalized by `_v3_node_output`; unsupported
expansion/blocking paths fail closed.

The CLIP, UNET, and VAE loader results are injected with `runner.seed` and are
therefore consumed as exact objects rather than executed again. The sampler
preparation closure executes model wrappers and ordinary preparatory nodes,
but its heavy-node scope is empty. Sampling then executes the sampler itself.

The fixture output stage validates that one `SaveImage` exists and that its `images`
input is the selected `1178 / Any Switch (rgthree)` branch. It executes node
1178 only and performs the upstream-compatible `255 * image`, clip, `uint8`,
PIL PNG, `compress_level=1` encoding itself. The serialized `107 / Image
Comparer (rgthree)` and its alternate branch are not executed by this fixture
path.

## Exact per-entry classification

The classification is per serialized entry. Generated IDs beginning with
`935:` are serialized representations of the dynamic/subgraph expansion and
are counted individually. The `1149:` entries are present in the serialized
file but have no parent or consumer in the retained runtime payload and do not
appear in RV2B execution evidence.

| ID | Class type | Classification | Evidence / reason |
|---|---|---|---|
| `9` | `SaveImage` | `VALIDATED_NOT_EXECUTED` | Output contract is checked; Golden encodes the PNG itself. |
| `62` | `CLIPLoader` | `GOLDEN_SEEDED_HEAVY_NODE` | Seeded before CLIP forward and later closures. |
| `66` | `UNETLoader` | `GOLDEN_SEEDED_HEAVY_NODE` | Seeded before sampler preparation. |
| `67` | `CLIPTextEncode` | `GOLDEN_EXECUTED` | RV2B CLIP closure evidence. |
| `80` | `JoinStrings` | `GOLDEN_EXECUTED` | CLIP dependency closure. |
| `84` | `Anything Everywhere` | `GLOBAL_SIDE_EFFECT` | V3 global-provider node; no output and no Golden execution event. |
| `85` | `Anything Everywhere` | `GLOBAL_SIDE_EFFECT` | V3 global-provider node; no output and no Golden execution event. |
| `88` | `EmptySD3LatentImage` | `GOLDEN_EXECUTED` | Sampler dependency closure; V3 result normalization applies. |
| `107` | `Image Comparer (rgthree)` | `UI_DISPLAY_ONLY` | UI comparer/output surface; not in the 32-node Golden execution set. |
| `137` | `CacheDiT_Model_Optimizer` | `GOLDEN_EXECUTED` | Sampler model-wrapper closure. |
| `151` | `ModelPatchLoader` | `UNREACHABLE_UNUSED` | Present in the 60-node request, but no links/consumers and no event evidence. |
| `175` | `VAEDecode` | `GOLDEN_EXECUTED` | Decode closure and retained output-branch event. |
| `191` | `ConditioningZeroOut` | `GOLDEN_EXECUTED` | Sampler conditioning dependency closure. |
| `199` | `SystemNotification\|pysssss` | `UI_DISPLAY_ONLY` | Notification UI output; not executed by Golden. |
| `202` | `easy globalSeed` | `UI_DISPLAY_ONLY` | `OUTPUT_NODE` no-op/control surface; not in execution evidence. |
| `214` | `Any Switch (rgthree)` | `GOLDEN_EXECUTED` | Selected latent branch in sampler closure. |
| `937` | `easy int` | `GOLDEN_EXECUTED` | Steps dependency. |
| `987` | `Any Switch (rgthree)` | `STANDARD_LINK_REACHABLE` | Alternate comparer branch input; not selected by Golden. |
| `993` | `CombineHooks8` | `UNREACHABLE_UNUSED` | No retained consumer or execution event. |
| `1014` | `PairConditioningSetProperties` | `GOLDEN_EXECUTED` | Positive/negative conditioning dependency. |
| `1045` | `ImpactIfNone` | `GOLDEN_EXECUTED` | Lazy-control dependency used by selected sampler inputs. |
| `1049` | `easy showAnything` | `UI_DISPLAY_ONLY` | Display-only terminal; not in Golden closure. |
| `1052` | `easy ifElse` | `GOLDEN_EXECUTED` | Selected steps-to-run lazy control. |
| `1063` | `StringToCombo\|LP` | `STANDARD_LINK_REACHABLE` | Nonselected lazy `sampler_mode` branch. |
| `1064` | `easy ifElse` | `GOLDEN_EXECUTED` | Sampler-mode selection. |
| `1065` | `StringToCombo\|LP` | `GOLDEN_EXECUTED` | Selected sampler-mode lazy branch. |
| `1066` | `easy showAnything` | `UI_DISPLAY_ONLY` | Display-only terminal; not in Golden closure. |
| `1067` | `easy showAnything` | `UI_DISPLAY_ONLY` | Display-only terminal; not in Golden closure. |
| `1073` | `PrimitiveFloat` | `UNREACHABLE_UNUSED` | No retained consumer or execution event. |
| `1094` | `SimpleMath+` | `STANDARD_LINK_REACHABLE` | Dependency of nonselected lazy `1052` branch. |
| `1132` | `Any Switch (rgthree)` | `STANDARD_LINK_REACHABLE` | Alternate B-side comparer branch; not selected. |
| `1137` | `easy imageSize` | `UI_DISPLAY_ONLY` | `OUTPUT_NODE` display surface; not in Golden closure. |
| `1178` | `Any Switch (rgthree)` | `GOLDEN_EXECUTED` | Selected output pass-through; explicit RV2B event. |
| `1242` | `ClownsharKSampler_Beta` | `GOLDEN_EXECUTED` | `sampling_start`, step, and `sampling_end` evidence. |
| `1254` | `SimpleMath+` | `STANDARD_LINK_REACHABLE` | Nonselected lazy `1052` branch. |
| `1262` | `LGNoiseInjectionLatent` | `GOLDEN_EXECUTED` | Runtime request points directly to 1499; sampler model wrapper executes. |
| `1277` | `VAELoader` | `GOLDEN_SEEDED_HEAVY_NODE` | Seeded before decode; source/H2D load is performed by the Golden stage. |
| `1281` | `LayerUtility: PurgeVRAM V2` | `GLOBAL_SIDE_EFFECT` | `clear_memory()` and optional model unload; explicitly not in Golden path. |
| `1297` | `easy float` | `UNREACHABLE_UNUSED` | No retained consumer or execution event. |
| `1299` | `easy float` | `STANDARD_LINK_REACHABLE` | Dependency of nonselected lazy `1052` branch. |
| `1302` | `Any Switch (rgthree)` | `STANDARD_LINK_REACHABLE` | Alternate output of the nonselected `1094` branch. |
| `1402` | `easy float` | `GOLDEN_EXECUTED` | Sampler eta dependency. |
| `1404` | `easy int` | `GOLDEN_EXECUTED` | Selected `1052` lazy branch. |
| `1484` | `ModelSamplingAuraFlow` | `GOLDEN_EXECUTED` | Sampler model-wrapper closure. |
| `1497` | `PrimitiveStringMultiline` | `GOLDEN_EXECUTED` | CLIP text dependency. |
| `1499` | `PathchSageAttentionKJ` | `GOLDEN_EXECUTED` | Runtime sampler model path and RV2B execution list. |
| `1501` | `ComfySwitchNode` | `UNREACHABLE_UNUSED` | Absent from exact 60-node request; request rewires 1262 directly to 1499. |
| `1149:1138` | `easy indexAnything` | `UNREACHABLE_UNUSED` | Orphan generated/aliased entry; no parent/consumer or RV2B event. |
| `1149:1146` | `easy stringToIntList` | `UNREACHABLE_UNUSED` | Orphan generated/aliased entry; no parent/consumer or RV2B event. |
| `1149:1147` | `CustomCombo` | `UNREACHABLE_UNUSED` | Upstream V3 orphan entry; no parent/consumer or RV2B event. |
| `935:449` | `easy stringToIntList` | `GOLDEN_EXECUTED` | Dynamic/subgraph sampler closure entry. |
| `935:481` | `easy indexAnything` | `GOLDEN_EXECUTED` | Dynamic/subgraph sampler closure entry. |
| `935:482` | `easy indexAnything` | `GOLDEN_EXECUTED` | Dynamic/subgraph sampler closure entry. |
| `935:919` | `CustomCombo` | `GOLDEN_EXECUTED` | Upstream V3 dynamic/subgraph entry. |
| `935:926` | `EmptyImage` | `GOLDEN_EXECUTED` | Dynamic/subgraph dependency. |
| `935:928` | `ImageRotate` | `GOLDEN_EXECUTED` | Dynamic/subgraph dependency. |
| `935:929` | `ImpactSwitch` | `GOLDEN_EXECUTED` | Dynamic/subgraph dependency. |
| `935:930` | `SimpleMath+` | `GOLDEN_EXECUTED` | Dynamic/subgraph dependency. |
| `935:931` | `easy imageSize` | `GOLDEN_EXECUTED` | Dynamic/subgraph dependency; UI payload is incidental to execution. |
| `935:932` | `CustomCombo` | `GOLDEN_EXECUTED` | Upstream V3 dynamic/subgraph entry. |
| `935:933` | `easy stringToIntList` | `GOLDEN_EXECUTED` | Dynamic/subgraph dependency. |

### Count reconciliation

| Classification | Count |
|---|---:|
| `GOLDEN_EXECUTED` | 32 |
| `GOLDEN_SEEDED_HEAVY_NODE` | 3 |
| `VALIDATED_NOT_EXECUTED` | 1 |
| `STANDARD_LINK_REACHABLE` | 7 |
| `REGISTRATION_ONLY` | 0 |
| `GLOBAL_SIDE_EFFECT` | 3 |
| `UI_DISPLAY_ONLY` | 7 |
| `UNREACHABLE_UNUSED` | 8 |
| `UNKNOWN` | 0 |
| **Total serialized entries** | **61** |

The 32 executed entries include the 11 `935:` dynamic entries. Seeded loaders
are deliberately excluded from the executed count. The 60-node runtime request
contains the 32 executed entries, three seeded heavy entries, and the remaining
nonexecuted entries; serialized `1501` is the sole pre-request omission.

## Special semantics resolved

### `LayerUtility: PurgeVRAM V2`

`ComfyUI_LayerStyle/py/purge_vram.py:40-69` shows that the node calls
`clear_memory()` and, when configured, `unload_all_models()` and
`soft_empty_cache()`. It returns its input and is an output node. The observed
fixture path never traverses this terminal; treating its serialized presence as execution would
invent a model-unload side effect. Its classification is
`GLOBAL_SIDE_EFFECT`.

### `SaveImage`

`golden_output` validates exactly one `SaveImage` node and its image socket, but
the fixture does not invoke its class function (`golden_serial.py:6120-6215`). It executes
the selected `Any Switch (rgthree)` node 1178 and encodes the image with the
same core PNG conversion parameters. `SaveImage` is therefore
`VALIDATED_NOT_EXECUTED`, not `GOLDEN_EXECUTED`.

### `SystemNotification|pysssss`

The class is an `OUTPUT_NODE`, returns UI message metadata, and has no role in
the fixture stage list. It is `UI_DISPLAY_ONLY`; its package is not
execution-required for the observed closure.

### `rgthree Image Comparer` and `Any Switch`

The selected 1178 `Any Switch (rgthree)` is executed and is required for the
output branch. The 1132 switch and 987 input belong to the alternate comparer
B-side topology and are only `STANDARD_LINK_REACHABLE`. The 107 comparer is a
UI display/output surface and is not executed. The retained RV2B event names
`saveimage_node=9`, `passthrough_node=1178`, and
`passthrough_class=Any Switch (rgthree)`; it does not show an executed comparer
node.

The production workflow helper can rewrite a comparer to
`ComfyModalProductionImageComparerOutput`, but that is a separate output
compilation surface. It is not evidence that the fixture's serial runner
invokes the comparer.

### Easy-use display/show and global nodes

`easy showAnything`, `easy imageSize`, and `easy globalSeed` are output/UI
surfaces. Their serialized presence does not make them part of the fixture
closure. The two `Anything Everywhere` V3 entries have no outputs and are
global-provider nodes; they are classified as `GLOBAL_SIDE_EFFECT` because
registration/provider behavior is distinct from ordinary link execution.

### Dynamic/lazy inputs and generated IDs

The retained list demonstrates both mechanisms:

* `1063` and the `1254 -> 1094 -> 1299/1302` topology are ordinary links but
  nonselected lazy branches. They remain `STANDARD_LINK_REACHABLE`, not
  executed.
* `935:*` entries are the dynamic/subgraph entries actually traversed and
  executed by the fixture. `GoldenSerialRunner._register_subgraph` installs
  expanded nodes and resolves their outputs immediately.
* `1149:*` entries are orphan serialized generated/aliased entries and are not
  present in the exact runtime payload's execution evidence.
* Runtime request ID normalization is string-based; no numeric coercion is
  used by the reference runner. V3 nodes are accepted only through the
  explicit `NodeOutput` normalization path.

### V1/V3 registration

ComfyUI registration remains broader than execution. `nodes.py:2240-2248`
registers V1 `NODE_CLASS_MAPPINGS` and display mappings; `nodes.py:2249-2279`
invokes V3 `comfy_entrypoint`, `on_load`, `get_node_list`, and schema
registration. `nodes.py:2300-2323` still attempts each eligible top-level
custom-node entry. The fixture adapter receives the resulting installed
mapping (`modal_app.py:21211-21215`); it does not independently load packages.

Therefore class registration, import-time package side effects, and node
execution are separate facts. This is why no node is assigned
`REGISTRATION_ONLY` in the exact observed node set, while registration remains
a package-level implementation concern. A package may be needed to register a
class or provider even when a particular node instance is not executed.

## Generic semantic handling rules

The exact classifications above are retained as fixture observations. A
generic workflow closure should interpret their underlying semantics as
follows:

* **Graph-global nodes/hooks:** discover provider nodes, hooks, and graph-wide
  callbacks from workflow semantics and package metadata, including cases with
  no ordinary output link. Initialize their providers when the workflow
  requires them; do not confuse provider registration with node execution.
* **Registration-only classes:** include a class/package in the closure when
  parsing, validation, display/schema registration, or alias resolution needs
  it, even if its instance will not execute. This does not make it an
  execution dependency or justify changing the installed environment.
* **Generated/aliased IDs:** retain IDs as strings and resolve generated,
  expanded, and aliased identities through their parent/subgraph and class
  metadata. Never infer reachability from numeric coercion or serialized
  presence alone.
* **V1/V3:** cover V1 class/display mappings and V3 entrypoint, load,
  node-list, schema, and `NodeOutput` normalization paths during discovery and
  validation. A V1/V3 distinction is a registration/execution semantic, not a
  Golden-only branch.
* **Sampler/scheduler registrations:** treat sampler and scheduler classes,
  registries, model-wrapper hooks, and related package registrations as
  closure requirements when the workflow selects them, even when the final
  sampler call is later in the execution order.
* **Package side effects:** record import-time registrations, extensions,
  web routes, threads, configuration writes, native loads, and other side
  effects as package metadata. Initialize them once per process as needed;
  do not unload registrations.
* **Preprocessing:** include workflow rewrites, normalization, output
  compilation, and other pre-execution transformations in the closure and
  validate their resulting graph before execution.
* **Dynamic/lazy nodes:** preserve lazy input decisions, query lazy status when
  needed, and expand dynamic/subgraph nodes before resolving their outputs.
  Derived entries remain part of the workflow closure only when proven by the
  selected graph and contract.

## Package observations from the Golden fixture

The following package lists are observations from this Golden benchmark
fixture. They are evidence for seeding reusable package/class metadata, not
architecture, an import allowlist, or proof of transitive package minimality.
The installed/published environment remains complete for every workflow.

### A. Packages observed behind executed classes — 8

* `comfyui-easy-use`
* `ComfyUI-CacheDiT`
* `comfyui-impact-pack`
* `ComfyUI-KJNodes`
* `comfyui_essentials`
* `comfyui_lg_samplingutils`
* `RES4LYF`
* `rgthree-comfy`

These own at least one of the 32 fixture-executed custom-node classes. Upstream
core and `comfy_extras` are also required, but are not custom-node packages.
For a different workflow, this role is derived again from that workflow's
semantics and proven closure.

### B. Registration-only package observation — 1 class owner / 0 package-exclusive

`comfyui-custom-scripts` owns only the serialized `SystemNotification|pysssss`
instance in this workflow. That instance is UI-only and never executed. If the
exact serialized prompt must remain generically registrable, the package has a
registration-only role. That is a metadata distinction, not a recommendation
to remove or omit the package. Because registration and execution are
different contracts, it is not counted as execution-required.

### C. Global/side-effect package observations — 2

* `cg-use-everywhere` — `Anything Everywhere` global-provider entries.
* `ComfyUI_LayerStyle` — `PurgeVRAM V2` can unload models/clear memory if
  executed, although this instance is not executed by the fixture.

The import-time side effects of all packages must still be measured separately;
this role does not imply that only the named node module is imported or that
any package can be omitted from the complete environment.

### D. Packages not proven necessary by this fixture's execution — 0 owners

No package is declared absent or unnecessary from the complete installed/
published environment. The nonexecuted nodes are clear, but package `__init__`
code and generic registration behavior are not equivalent to node execution.
`comfyui-custom-scripts` and the two side-effect packages remain metadata
observations whose relevance is workflow-dependent.

### E. Unknown at package-import-closure level — all 12 package internals

Node role is no longer unknown, but exact nested import closure, import-time
threads/routes/config writes, optional modules, and native/third-party loading
remain unmeasured for the 12 artifact-attributed packages. This is a package
metadata/closure question, not a reason to relabel the 61 node entries as
unknown. The next evidence must compare broad discovery with any
workflow-derived initialization in isolated processes and record mappings,
V1/V3 outcomes, import failures/order, side effects, and resource state.

## Readiness gate

The fixture's execution/registration behavior is sufficiently classified to
plan the next experiment, but this report does not authorize a
Golden-specific initializer or a hardcoded package set:

1. The exact 60-node runtime payload is now retained and directly comparable.
2. The 61-to-60 discrepancy is resolved as serialized `1501` omission plus the
   request-level `1262.model -> 1499` rewrite.
3. RV2B event evidence proves 32 executed nodes, three seeded heavy nodes, the
   selected output switch, and deliberate SaveImage bypass.
4. The remaining risk is package registration/import behavior, not uncertainty
   about whether JSON entries executed.

Before implementation, run the isolated parity experiment described in RA11A:
compare complete discovery with workflow-derived initialization for
class/display mappings, V1/V3 registration, import order/failures,
extension/web/global side effects, preprocessing, and the exact fixture
output/durability contract. Do not use transient RA9C files as runtime
requirements. The generic path must initialize only requirements not already
available, preserve the monotonic `PROCESS_INITIALIZED_SET`, keep the
`INSTALLED/PUBLISHED_ENVIRONMENT` complete, and use complete discovery as the
fallback whenever closure proof fails.

Future follow-up ownership is intentionally separated:

* **RA11D** should audit reusable package metadata: class ownership, global
  hooks, registration and sampler/scheduler requirements, side effects,
  preprocessing, aliases, and safe workflow/content-identity cache keys.
* **RA11E** should only remove universally avoidable eager imports. It must not
  remove packages or registrations merely because this Golden fixture did not
  execute a node.

```text
RA11C_COMPLETE=YES
SERIALIZED_ENTRY_COUNT=61
RUNTIME_REQUEST_NODE_COUNT=60
DISCREPANCY_RESOLVED=YES
GOLDEN_EXECUTED_NODE_COUNT=32
VALIDATED_NOT_EXECUTED_COUNT=1
REGISTRATION_ONLY_COUNT=0
GLOBAL_SIDE_EFFECT_COUNT=3
UNREACHABLE_UNUSED_COUNT=8
UNKNOWN_SEMANTICS_COUNT=0
PURGE_VRAM_NODE_CLASSIFICATION=GLOBAL_SIDE_EFFECT
SAVEIMAGE_CLASSIFICATION=VALIDATED_NOT_EXECUTED
CANDIDATE_REQUIRED_PACKAGE_COUNT=8
SAFE_SELECTIVE_IMPORT_IMPLEMENTATION_READY=NO
RUNTIME_SOURCE_MODIFIED=NO
MODAL_CONTACTED=NO
REPORT=RA11C_EXACT_GOLDEN_EXECUTION_CLOSURE_AUDIT.md
```
