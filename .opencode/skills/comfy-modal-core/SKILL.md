---
name: comfy-modal-core
description: Core engineering rules and architecture for the comfy-modal project. Use when changing comfy-modal source, Modal images, dependencies, custom-node packaging/sync, Golden execution code, model loading, restore/snapshot behavior, telemetry, deployment infrastructure, or performance experiments. For actual Golden deploy/run/validation operations, also load comfymodal-golden-ops.
---

# Comfy-Modal Core

This skill is the project's engineering constitution.

Use it for changes to comfy-modal itself. Keep task-specific prompts focused on the task; do not make every prompt retell project history.

When deploying, running, validating, or benchmarking a Golden path, **also load `comfymodal-golden-ops`**. That skill owns the current operational procedure. This skill owns the architectural rules behind it.

When current source and this skill disagree, investigate before assuming either one is right. Preserve intentional newer architecture and update this skill when a durable project rule genuinely changes.

---

## 1. General engineering style

### Keep important paths simple

Prefer explicit, inspectable code over clever machinery.

A useful rule of thumb:

> If a future agent cannot tell what work happens, when it happens, and who owns it by reading the main path, simplify it.

Avoid:
- hidden background work;
- multiple implementations of the same responsibility;
- "just in case" reloads, reinstalls, rereads, or cleanup;
- broad compatibility scaffolding around behavior we no longer use;
- god-file behavior that silently reaches into unrelated subsystems.

Reuse upstream ComfyUI/Modal primitives when they fit the contract. Own only the behavior we actually need to control.

### One responsibility, one owner

Important system responsibilities should have one canonical implementation.

Examples:
- image construction;
- package installation;
- source packaging;
- custom-node generation identity;
- Golden execution;
- deployment/run control;
- durability;
- telemetry definitions.

If two paths do the same job, consolidate them or clearly designate one as compatibility-only.

### Fail visibly when correctness matters

Do not silently fall back from an explicitly requested fast/correct path to another implementation and then report success.

For correctness-critical or benchmark-critical paths:
- requested implementation and actual implementation must be observable;
- fallback must be counted/classified;
- an unexpected fallback should normally fail the experiment.

Development conveniences may be more permissive, but they must not leak into Golden or production validation unnoticed.

---

# 2. Modal Images and dependencies

## Dependencies have one canonical owner

Python/system dependency installation belongs in the canonical image/dependency builder.

Do **not** scatter:
- `pip install`;
- `python -m pip install`;
- `uv pip install`;
- subprocess-driven package installation;
- custom-node startup installation;
- opportunistic "repair" installs;
- package auto-install on import/runtime

through normal project code.

Runtime code should validate required dependencies and fail with a useful error rather than modifying its environment.

A deliberately named development-only repair mode may exist, but it must be clearly isolated from production/Golden behavior.

## Build the image from stable to volatile

Expensive, rarely-changing layers should come before frequently-changing source/configuration.

Conceptually:

1. OS / CUDA / Python foundation
2. core pinned dependency stack
3. custom-node third-party dependency environment
4. accelerator/native packages that genuinely depend on the foundation
5. build-time validation that truly needs to be baked
6. ordinary custom-node source
7. comfy-modal runtime source
8. experiment/debug/runtime configuration that does not need to invalidate earlier work

The exact ordering may evolve, but the principle does not:

> A normal comfy-modal source edit must not reinstall unchanged third-party dependencies.

A stable child layer is not cacheable if its parent changes every deploy. When diagnosing rebuilds, inspect the **whole image DAG**, not just the changed layer's own files.

## Dependency identity should contain dependencies, not source noise

Dependency cache inputs should be deterministic and limited to things that can change the installed dependency environment.

Ordinary implementation source, logs, reports, timestamps, generated run state, benchmark artifacts, local worktree metadata, and unrelated configuration should not invalidate a dependency layer.

Be especially careful with local/editable path requirements. Do not let hundreds of mutable source files become part of the shared dependency hash just because a requirements file contains a local path. Separate third-party dependency resolution from ordinary local source whenever practical.

## Bake local files only when the image build needs them

Use Modal's runtime-mounted/local-source behavior for files that do not need to participate in a later image-build step.

Use baked `copy=True` only when there is a concrete reason the file must exist during image construction.

Do not create long chains of tiny image descendants by adding related files/modules one at a time when one logical addition can do the job.

## Cache behavior is a contract

Normal deploys must not silently enable cache-bypass mechanisms such as force-build/ignore-cache modes.

If a cache-bypass mode exists for debugging:
- make it explicit;
- log it prominently;
- keep it out of normal deployment defaults.

Tests should prove semantic invalidation:

- identical deploy -> unchanged expensive dependency work is reused;
- ordinary runtime source edit -> unchanged dependencies are reused;
- ordinary custom-node source edit -> unchanged dependencies are reused;
- real dependency input change -> dependency layer rebuilds;
- no duplicate package-install mechanism runs afterward.

Do not consider a staged-file hash unit test sufficient proof of real Modal caching.

---

# 3. Source, packaging, and custom nodes

## Resolve source deliberately

Keep these concepts separate:

- local source/build paths;
- packaged source identity;
- remote runtime paths.

A Windows host path is not a semantic remote ComfyUI path.

Resolve repository/ComfyUI/custom-node/comfy-modal roots deterministically. If source context is ambiguous, fail early with useful diagnostics rather than guessing a different checkout.

## One packaging policy

Image copying, deployment fingerprints, archive/source packaging, custom-node publication, and relevant generated-file discovery should share one canonical inclusion/exclusion policy.

Keep mutable or irrelevant junk out, including as appropriate:
- `.git`;
- nested worktrees / `.slim`;
- caches and virtual environments;
- `node_modules`;
- benchmark artifacts;
- reports and large logs;
- temporary/generated run state;
- credentials/secrets;
- recursively duplicated custom-node trees.

Do not maintain several subtly different ignore lists.

## Custom-node source and dependencies are different identities

A custom-node source change does not automatically mean its Python dependency environment changed.

Track separately:
- source generation/content identity;
- dependency identity;
- installed dependency environment.

Custom-node synchronization should be idempotent and content/generation based. Exact generation matches should skip expensive reload/copy work.

Do not repeat immutable deployment work on every restore/request "just to be safe."

### Shared custom-node ownership

The `comfyui-custom-nodes` Volume is a shared resource across Golden consumers.
The `comfyui-custom-nodes-publisher` authority owns its content; consumer app
names must never derive the
publisher app, Volume identity, generation, or receipt content identity. Exact
receipt matches are checked before publisher lookup, archive construction, or
content upload. If a receipt is missing or stale, receipt-only recovery is
allowed only when the authoritative Volume generation exactly matches the
canonical desired generation; ambiguous state fails closed.

Receipt recovery requires authoritative **full published-content** identity.
Code/deployment identity is not sufficient proof of the full shared Volume
contents. Missing receipt does not mean missing content, but matching a narrow
source identity does not mean matching full content. Maintain one canonical
full-content generation across desired identity, publication, Volume readback,
and receipt recovery.

## Prefer deterministic semantic identity

Generation/fingerprint inputs must represent semantic state.

Avoid volatile inputs such as:
- timestamps;
- random IDs;
- filesystem metadata that does not affect behavior;
- process/container-specific values.

The same semantic source should produce the same semantic identity.

---

# 4. Golden Path architecture

## Golden is a family of paths, not one permanent schedule

There is currently a **Golden Serial** reference path.

A future **Golden Overlapped** path is planned.

Do not turn "Golden" into a synonym for "serial."

The rule is:

> **Golden Serial must remain deliberately serial. Golden Overlapped may introduce intentional, measured overlap.**

Future overlap should be explicit in the orchestration layer and should preserve the same correctness/evidence standards.

Do not sneak overlap into Golden Serial to improve its number.

## Golden functions are independent building blocks

The current architectural model is a set of explicit Golden functions, such as:

- request setup;
- CLIP load;
- CLIP forward;
- UNET load;
- sampler preparation;
- VAE load;
- sampling;
- sampler tail;
- decode;
- output;
- durable commit;
- teardown.

These functions should be independently understandable, measurable, and reusable by different Golden orchestrators.

Golden Serial composes them serially.

A future Golden Overlapped orchestrator should reuse the same trustworthy functions where possible and explicitly coordinate allowed overlap between them.

Do not bury cross-stage scheduling inside a function whose name suggests it owns only one stage.

## Keep the Golden implementation self-contained

The canonical Golden implementation is intentionally isolated from the historical comfy-modal implementation stack.

Prefer a self-contained Golden module (currently the `golden_serial.py` model) that may import:
- Python standard library;
- third-party packages;
- Torch;
- safetensors/PIL/Modal;
- upstream ComfyUI APIs;
- real external custom-node packages required by the workflow.

It should **not** casually import our old comfy-modal loader/preload/profiler/residency/coordination stack.

If a proven mechanism from older code is needed, port the narrow logic into the Golden implementation rather than wrapping a large legacy subsystem.

The purpose is to keep the reference path auditable and free of hidden side effects.

## Do not build a second generic PromptExecutor

The Golden driver only needs to execute the supported Golden workflow correctly.

Use upstream ComfyUI behavior for graph/node semantics where suitable.

Do not grow the Golden runner into a full independent replacement for ComfyUI's executor.

Unsupported workflow semantics may fail closed when they are not part of the canonical Golden contract.

---

# 5. Golden Serial

Golden Serial is the clean reference composition.

Each heavy stage owns its complete work and returns with its own asynchronous/internal work joined.

QD or other transport may use **internal** concurrency inside a stage. That does not violate serial composition as long as no future-stage work escapes the function boundary.

Golden Serial must not contain:
- cross-heavy-stage prefetch;
- background future-stage model loading;
- hidden future-stage GPU work;
- work shifted into another stage merely to improve a headline timer.

This rule applies to **Golden Serial only**. It does not forbid a separately designed Golden Overlapped path.

---

# 6. Model loading and GPU ownership

## One physical model source lifecycle

For a direct Golden loader, aim for one physical checkpoint-source lifecycle:

source/header
-> transport
-> CUDA backing/storage ownership
-> tensor views
-> model adoption
-> strict proof
-> ready

Avoid:
- second checkpoint rereads;
- duplicate model-sized H2D;
- hidden native loader fallbacks after direct loading;
- whole-model CPU materialization when the selected direct path does not require it.

## Prove adoption, do not infer it

A loader is not successful because it has a fast-path name.

Prove the things that matter for the specific loader:
- expected tensors/bytes;
- device;
- dtype;
- shape;
- storage/data-pointer identity where zero-copy/same-storage is required;
- owner lifetime;
- patcher/model object identity;
- no duplicate reads/H2D;
- no fallback.

If dynamic ModelPatcher behavior is a prerequisite, verify the actual runtime prerequisite and fail closed if absent. Do not add unrelated global monkey patches simply to satisfy the loader.

## Keep ownership alive for as long as adopted tensors need it

Direct CUDA-backed views need an explicit owner lifetime.

Do not release backing storage while a CLIP/UNET/VAE object still references it.

Teardown/resource release belongs to the owner of that lifetime.

---

# 7. Restore and snapshots

## Restore should be minimal

A strong default principle is:

> **Restore is empty by default. Expensive work must earn admission.**

Restore should mainly perform unavoidable rebinding/identity/state repair.

Treat large I/O, model hydration, H2D, compilation, expensive diagnostics, and repeated immutable-state reconstruction as suspicious unless they truly must occur before restore returns.

Classify questionable work as:
- must be in restore;
- move after restore;
- redundant/no-op;
- diagnostic only;
- unknown.

Do not call unexplained application work "Modal variance."

## Keep pre-Python restore separate from Python `restore()`

Always distinguish:
- platform snapshot materialization before Python executes;
- application-owned Python restore work.

Our code cannot execute before Python resumes, but snapshot contents can affect platform restore cost.

## Snapshot contents must be intentional

For the current model-free Golden CPU snapshot design, do not accidentally retain:
- CLIP/UNET/VAE weights;
- model-sized storage owners;
- QD/pinned transport owners;
- open checkpoint readers;
- active preload/request workers;
- request futures/tasks;
- mutable per-request state.

The snapshot should contain the intended runtime/import/configuration state and be quiescent at capture.

Do not introduce CUDA initialization into a CPU snapshot-capture path unless the snapshot design explicitly changes and is separately justified.

## Request-time snapshot experiment rule

For current Golden experiment operations, follow `comfymodal-golden-ops`.

The durable rule is:
- a request-time snapshot-capture request does not count;
- exactly the directly-following experiment request does not count;
- later requests on the same deployment are eligible again;
- a later capture re-arms the one-request guard;
- capture does not permanently taint the deployment or automatically require redeployment.

---

# 8. Timing, telemetry, and performance claims

## Measure semantic boundaries

A metric name is not proof of its boundary.

Every important timing should be understood as one of:
- **TOTAL** — entire semantic operation;
- **PARTIAL** — only part of it;
- **CONTAMINATED** — includes unrelated/overlapping work;
- **UNKNOWN** — boundary cannot be established.

For Golden functions, the authoritative function wall is normally:

> actual function entry -> actual return/raise

Child telemetry explains the wall; it does not replace it.

## Raw evidence outranks summaries

Telemetry has misclassified work before.

Keep complete raw logs/events needed to independently reconstruct the conclusion.

Do not report only a profiler's chosen summary when the raw sequence is available.

When telemetry and raw call order disagree, investigate and prefer the proven execution order.

## Reconcile decompositions

When breaking a stage into parts:
- reconcile children to the authoritative enclosing wall;
- identify residual explicitly;
- avoid double-counting nested spans;
- account for synchronization boundaries correctly.

For CUDA profiling, prefer events/stream-aware measurement that does not add synchronization inside every inner operation. Realize measurements at an already-required safe boundary where possible.

## Locate cost before optimizing it

A wall-clock breakdown is the entry point, not the conclusion. Before changing
anything:

- Establish the **critical path**, not the biggest stage. Overlapping stages sum
  to more than the request wall, so time inside an overlapped stage can be fully
  absorbed by a longer sibling and yield nothing.
- Prefer **totals over means**. A function called 318 times at 22 ms is 7 seconds,
  not 22 ms.
- Separate **inclusive from self** time. Inclusive wall contains callees, so
  totals are not additive down a tree; a large inclusive total with near-zero
  self is a wrapper, not a target.
- Treat blocking waits (`select`, `EpollSelector`, queue reads) as waiting, not
  CPU burn.
- A Python-only profiler cannot see GPU kernel time. A GPU-bound stage reads as
  waiting; do not conclude there is nothing to fix.
- An observed breakdown is a hypothesis. Confirm with an A/B run.

`comfymodal-golden-ops` owns the concrete profiling procedure and the decision
report format.

## Optimize the real endpoint

Microbenchmarks are useful capability evidence, not automatically production wins.

Primary performance work should ultimately improve the real requested endpoint, especially:
- Python resume -> `FIRST_RESULT_READY` for the default output mode, or
  Python resume -> `TRUE_FIRST_DURABLE_RESULT` for an explicit strict output
  durability experiment;
- complete semantic stage walls.

Do not "optimize" by:
- moving cost before the timer;
- moving it into snapshot capture;
- hiding it behind background work;
- changing the endpoint;
- accepting a partial subspan as the whole stage.

---

# 9. Exactness and experiment correctness

Exactness is a first-class requirement where the experiment says it is.

If an exact path is known to be achievable, an exactness failure means diagnose/redesign the implementation. Do not relax the gate to make a benchmark look good.

When intentionally comparing a numerically different algorithm/backend (for example approximate/quantized attention), separate:
- technical execution validity;
- performance;
- canonical exact-output match.

A candidate can be useful performance evidence without being an exact Golden replacement.

Never silently redefine the canonical result because a new backend is faster.

---

# 10. Output and durability

"Generated" and "durable" are different.

The current generated-output policy is
`docs/COMFYMODAL_OUTPUT_DURABILITY_POLICY.md`. It defines
`COMFYMODAL_OUTPUT_DURABILITY=off|strict`: missing/`off` means `off`, while an
invalid explicit value is a configuration error. Generated-output durability
is off by default. The default endpoint is:

```text
encode -> observed SHA/bytes -> FIRST_RESULT_READY -> return
```

The strict opt-in endpoint is:

```text
write/fsync -> Volume.commit -> reopen/hash proof
-> TRUE_FIRST_DURABLE_RESULT -> return
```

Therefore `true_durable`, commit, reopen, and hash proof are not universal
requirements for an output-off result. They are required for strict output
durability, and strict failure must not silently fall back to the default.
There is no persistent output worker, background durability work,
deduplication shortcut, or shortcut around either sequence.

The durability contract should clearly distinguish:
- output encoding;
- asset write;
- Volume commit;
- commit completion;
- reopen;
- byte/hash verification;
- true durable result;
- result assembly;
- remote return;
- client receipt.

Do not stamp a durable/result event before the operation it claims has actually completed.

When durability uses a Modal Volume:
- in strict generated-output mode, prove the asset path is inside the intended
  mount;
- commit successfully, reopen the committed object, and verify the bytes/hash
  required by the strict contract.

This distinction does **not** weaken S4/source-publication durability. Shared
custom-node publication, authoritative full-content identity, and its required
Volume/receipt readback remain mandatory in every mode.

For single-use Golden containers, avoid large post-durable cleanup. Process exit can own final model/CUDA reclamation when that is the selected lifecycle.

---

# 11. Deploying and running

## Use the operational skill

For current Golden deployment/run commands and structural acceptance rules, load:

`comfymodal-golden-ops`

Do not duplicate or bypass its public control plane because an internal script looks easier.

If that public interface is broken, repair the interface.

Never use `@fixer` for any remote Modal deployment or run. The deployment/run
operator must be the primary agent or another explicitly designated non-fixer
operator.

## Deploy-only means deploy-only

A deploy operation should:
- resolve source/config/app identity;
- build/publish the required source/image;
- deploy;
- persist deployment provenance;
- perform cheap identity/health verification;
- exit.

It should not secretly:
- generate an image output;
- run Golden;
- run generic inference;
- prime an unrelated benchmark;
- require a run artifact before calling the deploy successful.

## One Golden request per experiment invocation

Keep each request independently classifiable.

Do not hide a multi-run campaign inside one opaque backend call.

Run confirmation requests separately so snapshot lifecycle, provider/region, failures, and outliers remain visible.

## Protect production

Normal experiments use explicit experimental app identities.

Do not use the stable production app as a convenient test target.

Do not hardcode every future batch/app name into source. Validate experimental app identity generically.

## Deployment and request identity are different

Separate:
- deploy-relevant source/configuration identity;
- request/run-only experiment settings;
- passive diagnostics.

A run-only setting should not force a redeploy unless it actually changes deployed code/configuration.

A deploy-relevant change means the old deployment is stale for that candidate; stop collecting homogeneous evidence from it.

---

# 12. Evidence and artifacts

A successful process exit is not enough.

Important experiments should preserve enough identity to answer:
- what source was deployed;
- which app/class/method ran;
- which request/cohort this was;
- provider/region/image/snapshot/container identity;
- workflow/model identity;
- requested and actual optimization/backend;
- output identity;
- durability status;
- structural validity;
- fallback/degraded state;
- raw evidence location.

Use invocation-bound manifests/artifacts as authority.

Do not select "the newest file" by modification time and assume it belongs to the request.

Keep invalid attempts too:
- snapshot captures;
- directly-post-capture requests;
- platform failures;
- DNFs;
- exactness failures;
- slow valid outliers.

Do not silently discard evidence that makes the result less pretty.

---

# 13. Concurrency and repository safety

Parallelize read-only exploration freely when it helps.

For source mutation/deployment, use clear ownership.

Never:
- reset;
- stash;
- clean;
- revert;
- force-checkout;
- overwrite;
- delete

unfamiliar concurrent work just to make your lane clean.

If another agent is editing the same function/file, reconcile deliberately rather than replacing their version.

Do **not** create a branch or isolated worktree unless the user explicitly approves it first.

One agent should own a given deployment/integration sequence at a time.

---

# 14. Testing

Tests should protect meaningful contracts, not implementation trivia.

Useful tests include:
- image/dependency invalidation semantics;
- source packaging parity;
- no unauthorized runtime/package installers;
- exact routing;
- model adoption/ownership;
- no duplicate read/H2D;
- fail-closed fallback behavior;
- snapshot cleanliness/quiescence;
- stage ordering for Golden Serial;
- request-local state cleanup;
- durability ordering;
- artifact/source identity.

Avoid:
- inflating test counts;
- maintaining tests solely for deleted behavior;
- mock-only proof of behavior that depends on Modal runtime/image caching;
- tests that pass because they reproduce the same wrong telemetry assumption.

For deployment/cache changes, include real deploy validation. The semantic change should predict the actual build work performed.

For performance changes, local tests do not replace real structurally valid runtime observations.

---

# 15. Working with historical evidence

History is useful, but architecture names are not evidence.

When reusing a historical optimization:
1. find the exact source path that ran;
2. establish its state/model/backend/environment;
3. establish the real timing boundary;
4. distinguish capability proof from full production result;
5. verify that the current implementation still follows that path.

Do not say "QD4", "Sage", "FastSafe", "snapshot", or "cache hit" as if the label proves what executed.

Prefer:
- current source;
- raw artifacts/logs;
- exact historical source;
- reconciled reports

over agent summaries.

---

# 16. Keep this skill useful

This skill should describe durable engineering rules, not the current experiment.

Do not add:
- temporary batch IDs;
- one-off app names;
- transient benchmark values;
- current expected SHA values;
- short-lived debugging flags

unless they become permanent architecture.

Put operational details that naturally change over time in `comfymodal-golden-ops` or the relevant source/config instead.

When a durable rule changes intentionally, update this skill in the same work so future agents do not resurrect the old architecture.

## 17. Scope subagent rechecks to deltas

When using subagents for a recheck, especially an oracle review, make clear that the work is a **recheck**, not a first-pass review. The oracle should inspect only the new work and its relevant deltas from the already-checked baseline, rather than rechecking the entire task or codebase. Expand beyond those deltas only when they expose a concrete regression or dependency that must be verified.
