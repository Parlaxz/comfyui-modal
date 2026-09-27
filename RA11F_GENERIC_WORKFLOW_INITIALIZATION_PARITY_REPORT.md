# RA11F — Generic Workflow-Driven Initialization Parity Experiment

**Date:** 2026-08-30  
**Scope:** isolated-process experiment and harness only. No Modal operation,
deployment, production runtime wiring, normal ComfyUI discovery change, or
installed custom-node change was made.

## Decision

```text
GENERIC_SELECTIVE_INITIALIZATION_FEASIBLE=PARTIAL
PRODUCTION_WIRING_READY=NO
```

The experiment proves the control-plane mechanics in an isolated synthetic
published environment: a workflow can select a bounded P3/P4 metadata closure,
initialization can be monotonic and serialized, and an unsafe closure can
choose complete discovery before selective initialization. It does **not**
prove parity with the installed ComfyUI/custom-node environment because no
installed package initializer was imported and no model, GPU, Modal, or output
execution was run.

This is therefore evidence that a generic mechanism is testable, not approval
to wire selective initialization into production.

## 1. Harness design

The new RA11F-only harness is under `ra11f/` with focused tests under
`tests/test_ra11f_*.py`. It launches a fresh Python subprocess for each arm:

```text
python -m ra11f --arm FULL
python -m ra11f --arm DERIVED
python -m ra11f --arm FALLBACK
python -m ra11f --arm SEQUENCE
```

`--experiment` launches all four commands as separate fresh processes and
retains their complete JSON results. Each process creates a temporary,
synthetic published package tree. The tree is removed after that subprocess;
the installed ComfyUI and sibling custom-node trees are never imported or
modified.

The synthetic discovery adapter mirrors the observable narrow contract needed
for this experiment:

* ordered top-level package attempts;
* child imports and import failures that do not abort the complete loop;
* V1 mappings and display mappings;
* V3 node lists and schemas;
* `RELATIVE_PYTHON_MODULE`;
* aliases/generated IDs;
* collision/override recording;
* global registries/hooks/providers, preprocessing, routes, web directories,
  model paths, and mutable registries; and
* declared filesystem/background side effects.

This is deliberately an adapter, not a copy of the installed ComfyUI loader.
The raw artifact identifies that limitation and sets `real_package_parity` and
`modal_e2e` to false.

The resolver keeps the required sets distinct:

```text
WORKFLOW_RUNTIME_CLOSURE
INSTALLED/PUBLISHED_ENVIRONMENT  (complete synthetic package set)
PROCESS_INITIALIZED_SET          (monotonic, process-local)
```

It resolves class IDs as strings, aliases, generated IDs, prerequisites, role
metadata, global/preprocessing requirements, lazy/dynamic requirements, and
sampler/scheduler requirements. A package is eligible for selective
initialization only when its metadata says proof level P3 or higher and
`safe_to_lazy_initialize=proven`. Otherwise the resolver records
`unsafe_or_unknown` and immediately uses complete discovery.

The process state holds a re-entrant lock across admission, import, side
effects, and registration. An initializer that partially mutates state and
then fails is recorded in `partial_failures` and `attempted`; it is not
reported as cleanly uninitialized and is not retried.

## 2. Workflows and fixtures tested

### Fixture A — exact Golden request payload as source observation

Source: `latest_benchmark_workflow.json`, the RA11C-proven runtime payload.

The harness independently observed:

* 60 prompt entries;
* serialized/editor discrepancy represented by `clean_workflow.json` having
  61 entries;
* `1501` absent from the runtime payload; and
* `1262.inputs.model == ["1499", 0]`.

The profile retains only a compact generic metadata projection for the
experiment. It does not pretend that a synthetic `golden_fixture` record is
the twelve real installed packages or that the 60-node graph was executed.
The generated filler entries in this projection are harness representation,
not new Golden runtime logic.

### Fixture B — synthetic non-Golden workflow A

This fixture is intentionally synthetic because no suitable distinct real API
prompt fixture was found in the repository. It covers:

* a V1 class (`SyntheticV1`);
* a string alias (`v1-alias`); and
* two ordered owners of `CollisionNode`, proving last-registration-wins and
  retaining the collision error.

### Fixture C — synthetic non-Golden workflow B

This fixture is also explicitly synthetic and covers different semantics:

* V3 registration, node list, and schema;
* graph-global provider and preprocessing;
* selected lazy/dynamic generated ID;
* sampler/scheduler registries;
* model/attention hook;
* route, web-directory, model-path, and mutable-registry metadata.

It is evidence for those harness contracts only, not arbitrary real workflow
compatibility.

### Candidate files not counted as additional workflows

`c5_latest_benchmark_workflow.json` and `c5_latest_performance_workflow.json`
were inspected. They are identical to one another, each has 61 entries,
contains `1501`, and uses the editor-form `1262.inputs.model` reference to
`1501`. They are not distinct non-Golden runtime workflows and were not
counted as such.

The unsafe requirement is a separate fallback scenario, not a fourth workflow:
`UnsafeNode` has proof level P2, an unresolved dynamic import, and
`safe_to_lazy_initialize=unknown`.

## 3. FULL, DERIVED, and FALLBACK arms

All values below are from the retained machine-readable artifact, not a
summary inferred after the fact.

| Arm | Process | Selected behavior | Attempted | Initialized | Import failures | Module delta | Thread delta | FD delta | Output evidence |
|---|---|---|---:|---:|---:|---:|---:|---:|---|
| FULL | fresh subprocess | complete discovery | 10 | 9 | 1 synthetic partial failure | 27 | 0 | 0 | Golden exact contract: `UNPROVEN_NOT_EXECUTED` |
| DERIVED | fresh subprocess | selective `golden_fixture` closure | 1 | 1 | 0 | 3 | 0 | 0 | Golden exact contract: `UNPROVEN_NOT_EXECUTED` |
| FALLBACK | fresh subprocess | unsafe/unknown → complete discovery | 10 | 9 | 1 synthetic partial failure | 27 | 0 | 0 | synthetic-only |

The synthetic FULL and DERIVED relevant scoped states matched across all raw
parity fields listed below. FULL-only state was retained as out-of-scope; it
was not discarded to make the selective arm look equivalent.

`FULL` is the authority only within this synthetic adapter. It is not evidence
that the current installed `ComfyUI/nodes.py` path has been run by RA11F.

## 4. Registration and schema parity

The raw artifact compares the derived closure against FULL for:

* V1 class mappings;
* display mappings;
* V3 node list and schemas;
* `RELATIVE_PYTHON_MODULE`;
* aliases and generated IDs;
* sampler/scheduler registries;
* mutable registries;
* model/attention hooks;
* graph-global providers;
* preprocessing;
* routes and web directories;
* model paths;
* import order and failures;
* collision/override errors; and
* declared side effects.

All 19 scoped fields matched for the synthetic Golden projection. The FULL
state retains synthetic V1/V3/global/sampler/collision/unsafe/partial records
outside the derived closure, including the collision override and the sticky
partial failure. This demonstrates scope separation, not installed package
parity.

The exact real installed-package results are `UNPROVEN`: the harness did not
invoke real V1 `NODE_CLASS_MAPPINGS`, real V3 entrypoints/schemas, real
`RELATIVE_PYTHON_MODULE` values, or real package collision behavior.

## 5. Global-state parity

The synthetic B workflow caused the derived state to contain and retain:

```text
graph_global_providers: everywhere.provider
preprocessing: graph-global-normalize, expand-lazy-branch
samplers: synthetic_euler
schedulers: synthetic_normal
model_attention_hooks: synthetic_attention_hook
routes: /synthetic/global
web_dirs: web/global
model_paths: models/synthetic
mutable_registries: graph_providers, sampler_registry, scheduler_registry
V3 node/schema: SyntheticV3
generated ID: generated:lazy
```

The scoped synthetic FULL/DERIVED comparison passed. Real package global state
remains unproven, particularly the RA11D-sensitive behavior of
`cg-use-everywhere`, easy-use, Impact, KJ, LevelPixel, RES4LYF, rgthree, and
the other audited packages.

## 6. Side effects and resource state

The harness captures before/after:

* `sys.modules` and synthetic sandbox module names;
* process RSS where the platform exposes it;
* thread identity, liveness, daemon status, and non-daemon subset;
* observable executor/future/timer lists;
* open file descriptors where `/proc/self/fd` exists;
* route and model-path counts;
* declared package side effects;
* known synthetic package-owned filesystem mutations;
* import failures, warnings, and errors; and
* package initializer wall time.

Observed synthetic resource result:

* one live non-daemon `MainThread` before and after;
* zero thread delta;
* zero FD delta;
* no observable executor, future, or timer;
* no RSS value on this Windows run (`rss_bytes=null`); and
* FULL/FALLBACK retained the synthetic global marker mutation and synthetic
  partial-failure evidence.

These are supporting local measurements. They are not Modal restore, snapshot,
or endpoint measurements. Real package-created threads, routes, files,
sockets, caches, native state, and background resources remain unmeasured.

## 7. Monotonic multi-workflow sequence

One process ran:

```text
A → B → A → B
```

Observed state transitions:

| Step | Workflow | Initialized before | Initialized after | New pending closure |
|---:|---|---|---|---|
| 1 | A | empty | `synthetic_v1`, `synthetic_collision_early`, `synthetic_collision_late` | those three |
| 2 | B | A set | A set plus `synthetic_v3`, `synthetic_global`, `synthetic_lazy`, `synthetic_sampler` | those four |
| 3 | A | A+B set | unchanged | empty |
| 4 | B | A+B set | unchanged | empty |

The sequence recorded:

```text
monotonic_initialized_set=true
mappings_and_hooks_retained=true
duplicate_initialization_prevented=true
no_unload_reload_revision_swap=true
serialized=true
lock_scope=complete_package_initializer
max_concurrent_initializers=1
```

The separate partial-failure test proves that `synthetic_partial` remains in
`attempted` and `partial_failures`, is absent from `initialized`, and is not
re-imported. This is synthetic proof of the state-machine contract only; no
real package revision was swapped because no real package was loaded.

## 8. Unsafe and fallback behavior

The FALLBACK resolver sees `UnsafeNode` and records both:

```text
synthetic_unsafe lacks P3 closure proof
synthetic_unsafe is not proven safe to lazy initialize
```

Its selection trace is exactly:

```text
resolve → unsafe_or_unknown → complete_discovery
```

The complete discovery attempt occurs before any selective initialization is
authorized. It attempts all ten synthetic records, preserves the synthetic
partial failure, and validates the required unsafe class from the complete
mapping. This is the intended successful fallback behavior, not a selective
initialization failure to hide.

The real RA11D unsafe/unresolved package families remain conservative:

* unsafe-to-narrow: `cg-use-everywhere`, `comfyui-easy-use`, LevelPixel,
  RES4LYF, and rgthree;
* all 12 audited real package internals retain at least one unresolved import,
  side-effect, optional-branch, or runtime question; and
* Impact and KJ remain package-shim candidates, not authorized class-only
  imports.

## 9. Fresh-process measurements

The final artifact recorded these synthetic measurements:

| Arm | Closure-ready wall (ms) | Process wall (ms) | Module delta | RSS delta |
|---|---:|---:|---:|---|
| FULL | 92.212 | 129.979 | 27 | unavailable |
| DERIVED | 7.383 | 40.521 | 3 | unavailable |
| FALLBACK | 64.082 | 110.924 | 27 | unavailable |
| SEQUENCE | 0.000* | 61.752 | 19 | unavailable |

`SEQUENCE` has no single closure-ready boundary; its process wall is shown
only to retain the raw measurement. Values vary with process startup and
temporary-file/import overhead. The 3-vs-27 module delta is a synthetic
adapter result, not proof of savings for real custom-node packages. No Modal
E2E, restore, snapshot, or request latency claim is made.

## 10. Output and durability exactness

No image or other workflow output was generated. The Golden exact output
contract is explicitly recorded as:

```text
UNPROVEN_NOT_EXECUTED
models/GPU/Modal/output path were not run
```

No SHA comparison, `FIRST_RESULT_READY`, Volume commit, reopen proof, or
`TRUE_FIRST_DURABLE_RESULT` was fabricated. The current policy was respected:
normal output durability is off by default, while strict durability would
require write/fsync → commit → reopen/hash proof. S4 publication scope was not
exercised or changed.

## 11. Package metadata proof levels

The synthetic metadata contains ten records:

| Count | Meaning in this harness |
|---:|---|
| 8 P4 | Synthetic Golden, V1, V3, global, lazy, sampler, and collision records with behavioral harness proof |
| 1 P3 | Synthetic partial-failure record with bounded initializer behavior |
| 1 P2/unknown | Synthetic unsafe record, not eligible for selective initialization |

Thus the synthetic harness metadata achieved P3=9 and P4=8, with one synthetic
unsafe/unresolved record. These counts must not be read as proof about real
installed packages. For the real RA11D inventory, real package P3/P4 behavioral
authorization is **0/0** in this lane and all 12 remain unresolved at package
import-closure level. Five are explicitly unsafe-to-narrow on current evidence.

## 12. Discrepancies retained

1. `clean_workflow.json` has 61 entries while the exact Golden runtime payload
   has 60; `1501` is absent from the latter.
2. The runtime payload rewrites `1262.inputs.model` to `1499`; the C5 editor
   variants retain the `1501` form.
3. The Golden source observation is exact for count/omission/rewrite, but the
   harness execution projection is synthetic and compresses class metadata.
4. C5 benchmark/performance files are identical to each other and are not
   distinct non-Golden workflows.
5. FULL and FALLBACK include one deliberate synthetic partial import failure;
   DERIVED does not reach that out-of-scope package.
6. RSS is unavailable on this Windows process, so no RSS reduction claim is
   possible.
7. The synthetic adapter is not the installed ComfyUI discovery implementation
   and no real package initializer was imported.
8. No real V1/V3 mapping, global registry, preprocessing, route, filesystem,
   thread, FD, cache, native-resource, output, or durability parity was
   established.
9. The exact Golden output SHA contract remains untested in this lane.

## 13. Smallest safe next production experiment

Do not wire the resolver into the normal runtime yet. The smallest safe next
experiment is a separately invoked, non-production, fresh-process probe that:

1. copies the complete installed/published ComfyUI and custom-node environment
   into a disposable sandbox;
2. runs the actual current ComfyUI complete discovery in one process;
3. runs a generic metadata-driven candidate in another process, initially only
   for a package whose initializer, globals, ordering, and dynamic behavior
   are independently bounded to P3;
4. compares the same registration/global/resource fields from this report;
5. sends every unknown or RA11D-unsafe package through complete discovery;
6. runs a non-Golden real workflow using that package/class; and
7. rejects the candidate on any mapping/global/resource/output discrepancy.

The installed/published environment must remain complete. The process
initialized set must remain monotonic add-only. This probe should be an
explicit experiment entrypoint, not a new Golden runtime, not a package
modification, not a production default, and not a Modal deployment.

## 14. Why this remains generic

The resolver consumes workflow class IDs and generic package metadata records.
The same code handles V1, V3, aliases/generated IDs, global/preprocessing,
lazy/dynamic, sampler/scheduler, partial failures, collisions, and fallback.
The Golden profile is data under `ra11f/fixtures/`, used to validate the
workflow source count and rewrite only; there is no `golden_p1` conditional,
Golden-specific import path, package deletion, or production runtime hook.

## Raw artifacts and validation

Machine-readable raw output is retained at:

```text
ra11f/artifacts/ra11f_latest.json
```

The harness source and focused tests are:

```text
ra11f/harness.py
ra11f/__main__.py
ra11f/fixtures/golden_profile.json
tests/test_ra11f_resolver.py
tests/test_ra11f_process.py
tests/test_ra11f_subprocess.py
```

Validation run:

```text
python -m unittest tests.test_ra11f_resolver tests.test_ra11f_process tests.test_ra11f_subprocess -v
9 passed
python -m compileall -q ra11f tests/test_ra11f_process.py tests/test_ra11f_resolver.py tests/test_ra11f_subprocess.py
PASS
python -m ra11f --experiment ra11f/artifacts/ra11f_latest.json
FULL, DERIVED, FALLBACK, SEQUENCE subprocess return codes: 0
```

```text
RA11F_COMPLETE=YES
PRODUCTION_SOURCE_MODIFIED=NO
CUSTOM_NODE_SOURCE_MODIFIED=NO
MODAL_CONTACTED=NO

WORKFLOWS_TESTED=3
NON_GOLDEN_WORKFLOWS_TESTED=2

FULL_DISCOVERY_ARM=PASS
DERIVED_INITIALIZATION_ARM=PARTIAL
FALLBACK_ARM=PASS

V1_PARITY=UNPROVEN
V3_PARITY=UNPROVEN
GLOBAL_STATE_PARITY=UNPROVEN
PREPROCESSING_PARITY=UNPROVEN
RESOURCE_QUIESCENCE_PARITY=UNPROVEN

MONOTONIC_MULTI_WORKFLOW=PASS
UNKNOWN_CLOSURE_FALLS_BACK=YES

PACKAGES_P3=0
PACKAGES_P4=0
PACKAGES_UNSAFE_OR_UNRESOLVED=12

GENERIC_SELECTIVE_INITIALIZATION_FEASIBLE=PARTIAL
PRODUCTION_WIRING_READY=NO
GOLDEN_SPECIFIC_RUNTIME_CREATED=NO
S4_PUBLICATION_SCOPE_CHANGED=NO

REPORT=RA11F_GENERIC_WORKFLOW_INITIALIZATION_PARITY_REPORT.md
```
