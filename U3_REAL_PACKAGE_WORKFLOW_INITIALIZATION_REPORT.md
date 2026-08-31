# U3 — Real-Package Workflow-Driven Initialization

**Date:** 2026-08-31  
**Scope:** local ComfyUI/custom-node discovery only. No Modal, deployment,
remote execution, QD, CLIP residency, durability, sampling, output, or S4
changes were made by this lane.

## Decision

```text
REAL_PACKAGE_PARITY=UNPROVEN_FOR_LAZY_INITIALIZATION
PRODUCTION_WIRING_IMPLEMENTED=NO
```

The real installed package experiment does not authorize a production
selective initializer. The complete installed environment remains available,
and the existing normal ComfyUI startup path remains unchanged. The new probe
is an explicit, disposable experiment entrypoint rather than a runtime or
Golden bootstrap.

## 1. Evidence path

The probe is `ra11f/real_harness.py`, with focused coverage in
`tests/test_ra11f_real_packages.py`. It:

1. reads the canonical installed custom-node registry and verifies package
   trees exist;
2. copies the actual ComfyUI Python/runtime source and the actual package trees
   into a temporary sandbox;
3. starts a fresh child process for every FULL or SELECTIVE arm;
4. invokes the installed ComfyUI loader itself (`nodes.init_external_custom_nodes`
   for FULL and `nodes.load_custom_node` for package selection);
5. captures registrations, ownership, imports, loader directories, web
   directories, import failures, warnings, filesystem changes, threads, file
   descriptors, and timing; and
6. compares FULL state scoped to the selected package closure against the
   candidate process.

The live ComfyUI/custom-node trees are never imported by the child. Temporary
sandbox state is removed after each arm. The probe performs no workflow model
execution and does not contact Modal or the network.

The retained raw artifact is:

```text
ra11f/artifacts/ra11f_real_latest.json
```

## 2. Real package set

The installed registry contained **23 existing canonical package trees**. The
probe excludes the plugin itself and duplicate/generated Modal deployment
directories, matching the package-set policy used for the installed registry.
The audited package IDs were:

```text
cg-use-everywhere
ComfyUI-CacheDiT
comfyui-custom-scripts
comfyui-detail-daemon
comfyui-easy-use
ComfyUI-Flux2Klein-Enhancer
comfyui-impact-pack
ComfyUI-KJNodes
comfyui-levelpixel
comfyui-lora-manager
comfyui-manager
ComfyUI-SeedVR2_VideoUpscaler
comfyui-workflow-encrypt
comfyui_controlnet_aux
comfyui_essentials
comfyui_fill-nodes
comfyui_image_metadata_extension
ComfyUI_LayerStyle
comfyui_lg_samplingutils
comfyui_sam3
masquerade-nodes-comfyui
RES4LYF
rgthree-comfy
```

The source audit is deliberately conservative. Every package retains
`unknown_transitive_behavior=true`; no package was assigned P3 or P4 proof.
Observed source flags across the 23 records were:

| Signal | Packages flagged | Meaning |
|---|---:|---|
| Dynamic imports | 14 | `importlib`, `__import__`, or package/file discovery was present |
| Routes/hooks/lifecycle | 15 | route, hook, entrypoint, or lifecycle registration was present |
| Filesystem writes | 19 | writes, directory creation, or deletion was present |
| Reloads | 2 | `importlib.reload` was present |
| Unknown transitive behavior | 23 | source scan cannot prove the complete import/runtime closure |

Representative exact observations from the real source:

* `comfyui-custom-scripts/__init__.py` discovers and executes files under
  `py/` using dynamic file imports and synthetic module names.
* `comfyui-easy-use/__init__.py` dynamically imports route and node modules and
  creates or rewrites package-owned files/directories during initialization.
* `rgthree-comfy/__init__.py` eagerly imports server/node modules and removes
  old web directories during initialization.
* `RES4LYF/__init__.py` performs runtime imports and reloads.
* `ComfyUI-Flux2Klein-Enhancer/__init__.py` eagerly aggregates several node
  subpackages.
* The actual `nodes.load_custom_node()` mutates shared
  `NODE_CLASS_MAPPINGS`, display mappings, `RELATIVE_PYTHON_MODULE`,
  `LOADED_MODULE_DIRS`, and `EXTENSION_WEB_DIRS`; packages can additionally
  mutate server/global state through their imports.

For the remaining packages, the full child-process observations are retained,
but dynamic/transitive behavior, global hooks, and resource ownership were not
provable enough to claim safe narrowing. Import failures are retained as
evidence, not treated as successful or safe initialization.

## 3. Fresh-process results

The FULL arm used the actual current external loader. It attempted all 23
package records and observed:

| Observation | Result |
|---|---:|
| Package attempts | 23 |
| Successful package registrations | 9 |
| Package import failures | 14 |
| Registered class mappings | 413 |
| Loaded module directories | 9 |
| Extension web directories | 2 |
| Imported module names observed | 5,811 |
| Thread delta | 0 |
| File-descriptor delta | +4 |
| Sandbox files created | 9 |
| Sandbox files removed | 0 |

The failures are real local-environment evidence from the isolated copy. The
most common cause was the copied runtime's import resolution around optional
ComfyUI/server support modules; no package failure was hidden or repaired.
The created files were sandbox bytecode plus the
`comfyui-workflow-encrypt` web asset. No live installation files changed.

The local wall measurements are only import/process measurements. They are not
Modal restore timings, remote startup timings, or a claimed remote speedup.

## 4. Workflow arms

### Golden workflow

Input: `latest_benchmark_workflow.json`, the current real Golden request
payload. The probe observed 60 prompt entries and 39 distinct class IDs. Core
classes without a package owner are intentionally treated as unknown for
selection. Therefore the Golden SELECTIVE arm took the safe complete-discovery
fallback:

```text
resolve workflow classes
→ unknown owner(s)
→ complete real discovery
```

The fallback's scoped state matched FULL (`exact_scoped_match=true`), but this
is **not** a selective-initialization win: the complete loader ran. No model,
GPU execution, image output, SHA, or durability contract was exercised.

### Non-Golden workflow A

Deterministic discovery-only projection from a real FULL owner observation:

```text
class: CacheDiT_LTX2_Optimizer
package: ComfyUI-CacheDiT
```

The candidate loaded only that package through the real
`nodes.load_custom_node()` path. Scoped parity was false because the fresh
package import closure differed from the package's observation inside the
FULL process (including additional support-module imports). The package was
therefore unsafe to narrow.

### Non-Golden workflow B

Deterministic discovery-only projection from a different real FULL owner
observation:

```text
class: Flux2KleinColorAnchor
package: ComfyUI-Flux2Klein-Enhancer
```

This selected a materially different package from workflow A. Its scoped
candidate parity was also false, so it was unsafe to narrow.

These two projections are real class/package workflows for initialization
discovery, not synthetic package names. They were intentionally not executed
through model/GPU/output paths because no package reached safe authorization.

## 5. Parity and fallback decision

The comparison includes:

* V1 class mappings and class owners;
* display mappings;
* `RELATIVE_PYTHON_MODULE`;
* imported module names and package import order;
* import failures and warnings;
* `LOADED_MODULE_DIRS` and `EXTENSION_WEB_DIRS`;
* package resources and package-owned filesystem mutations; and
* route/hook/lifecycle observations available from the actual loaded package
  modules.

Results:

| Arm | Selection | Scoped match | Decision |
|---|---|---:|---|
| Golden | unknown core owner → complete discovery | Yes | Safe fallback; not selective |
| Non-Golden A | `ComfyUI-CacheDiT` only | No | Unsafe; package remains normal-init |
| Non-Golden B | `ComfyUI-Flux2Klein-Enhancer` only | No | Unsafe; package remains normal-init |

The probe's package controller is monotonic and never unloads or reloads a
package. Unit tests cover duplicate-safe admission, sticky complete fallback,
and no unload/reload behavior. Existing RA11 process tests cover serialized
initialization and sticky partial failures. This proves the controller
contract, not production authorization.

Package-granular fallback is retained: an explicitly selected package is
initialized through the normal ComfyUI package loader, and an unsafe package
does not by itself force unrelated packages to load. Complete discovery is
used only when the workflow contains an owner-unknown class, as happened for
the Golden payload.

## 6. Production decision

Production wiring was intentionally **not** implemented.

Reasons:

1. zero of 23 real packages has P3/P4 behavioral authorization;
2. both distinct real non-Golden candidate arms failed exact scoped parity;
3. 14 real package imports failed in the complete isolated process and must
   remain visible rather than being hidden by a new selector;
4. route/global/filesystem/reload behavior is present across the package set;
5. the Golden workflow contains core classes with no package owner, requiring
   complete discovery for correctness; and
6. class mapping metadata alone cannot prove transitive registration,
   resources, hooks, or execution dependencies.

Consequently, `comfyapp.py` continues to use the existing normal ComfyUI
startup/discovery path. No dedicated Golden bootstrap was added. Unknown
packages fail safely to normal initialization in the experiment mechanism;
no unsafe optimization was forced into production.

## 7. Validation

Passed:

```text
python -m ra11f.real_harness --experiment ra11f/artifacts/ra11f_real_latest.json
  structured result; status=ok

python -m unittest tests.test_ra11f_real_packages tests.test_ra11f_resolver tests.test_ra11f_process tests.test_ra11f_subprocess tests.test_dependency_resolver -v
  27 passed

python -m pytest tests/test_runtime_bootstrap.py tests/test_p2_golden_core_contract.py -q
  43 passed, 1 skipped

python -m unittest tests.test_custom_node_generation_parity.TestGenerationParityScenarios -v
  18 passed

python -m py_compile ra11f/real_harness.py tests/test_ra11f_real_packages.py
python -m compileall -q ra11f tests/test_ra11f_real_packages.py tests/test_ra11f_process.py tests/test_ra11f_resolver.py tests/test_ra11f_subprocess.py
  passed
```

A broader concurrent worktree sweep was not used as a U3 gate: the existing
worktree contains unrelated QD/CLIP edits, and the volume/auto-warmup sweep
reported concurrent version/expectation failures and timed out. Those files
were not modified by U3.

## Final lane status

```text
U3_COMPLETE=YES
REAL_PACKAGES_AUDITED=23
PACKAGES_SAFE_TO_NARROW=0
PACKAGE_GRANULAR_FALLBACK=YES
PRODUCTION_WIRING_IMPLEMENTED=NO
GOLDEN_WORKFLOW_PASS=YES
NON_GOLDEN_WORKFLOWS_PASS=0
GOLDEN_SPECIFIC_BOOTSTRAP=NO
QD_CODE_CHANGED=NO
CAST_ONCE_CODE_CHANGED=NO
MODAL_CONTACTED=NO
READY_FOR_REMOTE_STARTUP_TEST=NO
```
