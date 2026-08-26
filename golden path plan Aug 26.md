# Golden Path Plan — Aug 26, 2026

> **Purpose:** Authoritative scope and engineering contract for the ComfyUI Modal **Serial Golden Path** work.
>
> This file is written so a fresh implementation/audit agent can understand the target without access to prior conversation history.
>
> **Do not treat the current production path as the target architecture.** The Golden Path is a deliberately simple, inspectable reference implementation assembled from the strongest previously proven mechanisms.

---

## 1. Mission

Build one deterministic, exact, **strictly serial** ComfyUI-on-Modal request path that is easy to reason about, easy to measure, and fast enough to become the reference implementation.

The Golden Path exists to answer two questions cleanly:

1. **What is the fastest exact serial composition we can achieve when each stage is implemented correctly?**
2. **Where is time actually spent when every heavy stage owns its complete work and no future-stage work is hidden elsewhere?**

The system must optimize the real end-to-end request, not isolated microbenchmarks or profiler labels.

### Hard performance gates

- **Modal/Python restore:** `<= 3.0 s`
- **Remote Python resume -> TRUE FIRST DURABLE RESULT:** `< 10.0 s`
- **Canonical exact output SHA-256:**
  `20b10e1f99831bc758d9df82f43ce0beb1cbc636a740d11a29eb2bffe90e5260`
- **Near-zero app-owned post-durable work** on single-use containers.
- Scale-to-zero / single-use behavior remains supported.

These are engineering targets, not permission to violate correctness or measurement semantics.

---

## 2. Core philosophy

### Build complex things as simply as possible

The Golden Path should reduce:

- moving parts,
- hidden state,
- wrappers,
- indirection,
- background scheduling,
- lifecycle ambiguity,
- compatibility scaffolding,
- legacy execution paths.

A boring explicit function call is preferred over a clever invisible mechanism.

### Prove the real thing

Do not substitute any of the following for real end-to-end evidence:

- architecture names,
- "fast path" labels,
- profiler summaries,
- test counts,
- isolated microbenchmarks,
- cache-warm measurements,
- hidden prefetch work,
- snapshot-shifted model cost.

Exact source, raw artifacts, runtime behavior, and complete semantic boundaries outrank summaries.

### Exactness failures mean redesign/fix, not abandonment

The canonical exact image is known to be achievable. If an implementation is not exact, diagnose and fix the implementation.

Do not relax exactness merely to make a benchmark look better.

---

## 3. Authority and evidence order

When sources disagree, use this precedence:

1. **Exact current source / raw runtime artifacts / exact logs**
2. **This Golden Path plan and reconciled source-of-truth decisions**
3. **Phase reports / amendments**
4. **Agent summaries**
5. **Profiler labels or inferred architecture names**

User acceptance/explicit architectural decisions are authoritative.

### Measurement labels

Every timing claim must be classified accurately.

A number may represent:

- **TOTAL** — entire semantic operation,
- **PARTIAL** — only one component,
- **CONTAMINATED** — includes unrelated or overlapping work,
- **UNKNOWN** — boundary cannot be established.

Never call a number total merely because its metric name sounds total.

---

## 4. The Serial Golden Path

The conceptual runtime is:

```text
PLATFORM SCHEDULING / PRE-PYTHON RESTORE
        ↓
REMOTE PYTHON RESUME
        ↓
REAL POST-SNAPSHOT RESTORE
        ↓
golden_request_setup()
        ↓
golden_clip_load()
        ↓
golden_clip_forward()
        ↓
golden_unet_load()
        ↓
golden_sampler_prepare()
        ↓
golden_vae_load()
        ↓
golden_sampling()
        ↓
golden_sampler_tail()
        ↓
golden_vae_decode()
        ↓
golden_output()
        ↓
golden_durable_commit()
        ↓
COMMITTED OBJECT REOPEN / SIZE / HASH VERIFICATION
        ↓
TRUE_FIRST_DURABLE_RESULT
        ↓
RESULT ASSEMBLED
        ↓
golden_teardown()
        ↓
ACTUAL REMOTE RETURN / YIELD
        ↓
CLIENT RESULT RECEIVED
```

### Absolute seriality rule

**No cross-stage heavy overlap.**

Forbidden examples:

- UNET source reads during CLIP forward,
- VAE preload during sampling,
- CLIP hydration during restore,
- future-stage model prewarm,
- background QD readers surviving a stage return,
- speculative model loads,
- stage-shifting work purely to make one metric look faster.

Internal parallelism **inside one stage** is allowed when useful, but:

- all workers must be joined,
- all required futures must be done,
- all required CUDA completion events must be waited,
- no candidate-owned work may remain pending,
- the function must not return until its semantic operation is ready.

---

## 5. Snapshot architecture

### Golden snapshot is runtime-only

The Modal CPU memory snapshot may contain:

- Python imports,
- registered node classes,
- lightweight immutable metadata,
- dependency/runtime initialization,
- safe static runtime state,
- non-model configuration.

It must **NOT** contain CLIP, UNET, or VAE model weights.

At the actual snapshot pre-capture boundary, prove:

- UNET model-weight bytes = `0`
- CLIP model-weight bytes = `0`
- VAE model-weight bytes = `0`
- loaded UNET count = `0`
- loaded CLIP count = `0`
- loaded VAE count = `0`
- QD owner count = `0`
- open checkpoint payload readers = `0`
- model preload workers = `0`
- model prefetch futures = `0`

### Do not load then evict

The Golden snapshot should not read model payloads and then discard them before capture.

The intended architecture is that model payload I/O occurs during the request where its cost is measured.

### Known current P1 violation

The current P1 deployment lifecycle has been observed doing:

- `clip_snapshot_load`
- `unet_snapshot_load`
- `vae_snapshot_load`
- retaining VAE,
- retaining a CPU NextDiT with 453 BF16 parameters,
- reporting `cpu_snapshot_models_present=1`,
- reporting `clip_present=1`,
- reporting `unet_present=1`,
- treating `expected_vae=1` / `expected_unet=1` as a production snapshot invariant PASS.

That behavior is **invalid for Golden** and must be removed/bypassed for the Golden profile.

A fast restore from a model-bearing snapshot does not make the architecture valid.

---

## 6. Restore semantics

Restore is not a request-time helper.

The authoritative restore boundary belongs to the actual Modal lifecycle and should include, where available:

- `remote_python_resume_wall_unix_ns`
- `restore_method_start_wall_unix_ns`
- `restore_method_end_wall_unix_ns`
- actual restore duration
- restore end -> remote method entry

Keep distinct:

1. platform scheduling,
2. pre-Python platform restore,
3. remote Python resume,
4. Python restore method,
5. restore-to-method-entry gap,
6. Golden request execution.

### Important current P1 bug

Current `golden_restore()` is merely request-time state observation and currently checks CUDA/thread state.

It is **not** the actual restore operation and must not be presented as the restore duration.

The Golden core should consume authoritative restore facts from the thin Modal adapter rather than fabricating them.

---

## 7. Canonical model-stage selections

There is no A/B test in the Golden baseline.

One implementation is selected for each section.

If a selected mechanism is structurally wrong, fix it.

If it is structurally correct but slow, report the truth first. Do not silently switch candidates mid-cohort.

---

## 8. CLIP load

### Selected mechanism

Use the **E37-class production QD4 loader** as the Golden CLIP load.

Requirements:

- file-backed,
- request-time,
- no CPU model-weight snapshot,
- one physical source lifecycle per checkpoint,
- direct CUDA backing ownership,
- direct tensor views,
- same-storage adoption,
- dynamic patcher semantics where required,
- no hidden native reread,
- no second model-sized H2D,
- no fallback.

Historical strongest whole-load evidence for E37 CLIP QD was roughly **1.15 s** for the complete load/hydrate/adopt path under its valid conditions.

This historical number is a reference, not a guaranteed current runtime result.

### Construction contract

Installed upstream ComfyUI behavior matters.

P1 established:

- `comfy.sd.CLIP` consumes explicit model options such as:
  - `initial_device`
  - `dtype`
  - `load_device`
  - `offload_device`
- construction must avoid triggering an unwanted later `load_models_gpu()` or second load.

### Dynamic patcher prerequisite

Upstream `comfy.model_patcher.CoreModelPatcher` defaults to legacy `ModelPatcher`.

The intended runtime with comfy-aimdo active rebinds it to `ModelPatcherDynamic` during startup.

Golden should verify the expected runtime contract rather than introducing an unrelated second global monkey-patch.

If same-storage adoption requires dynamic patcher semantics and the runtime prerequisite is absent, fail closed.

---

## 9. CLIP forward

### Selected mechanism

Use the known-good exact/quiet CLIP forward.

Requirements:

- actual CLIP forward executes,
- no conditioning cache may bypass the structural/cohort validation forward,
- no UNET source preparation during CLIP forward,
- no future-stage model work,
- exact canonical conditioning behavior.

Historical healthy E37 inner CLIP forward was about **1.11 s**.

Later 4+ second CLIP forward timings were contaminated/pathological and are not accepted as normal.

### Timing contract

`golden_clip_forward()` headline time must equal the actual function entry-to-return wall.

Do not add previous CLIP-load work to it.
Do not include future UNET work.
Do not reconstruct it from old profiler "pre-sampler" spans.

---

## 10. UNET

### Selected Golden implementation: Candidate A

Use:

**E27-style QD4 physical producer mechanics + direct persistent QD-owner same-storage production adoption**

The desired path is:

```text
safetensors header / metadata
    ↓
Lumina2 / NextDiT config detection
    ↓
NextDiT skeleton construction
    ↓
one QD4 / 32 MiB file -> pinned -> CUDA producer
    ↓
one contiguous CUDA backing owner
    ↓
tensor views
    ↓
load_model_weights(..., assign=True)
    ↓
strict shape/dtype/device/data_ptr proof
    ↓
persistent ModelPatcher
    ↓
sampler-usable Golden UNET ready
```

### Canonical UNET

- file: `z_image_turbo_bf16.safetensors`
- size: ~12.31 GB
- intended tensor/parameter count: `453`
- architecture: NextDiT / Lumina2
- exact canonical output required.

### Historical evidence

E27 proved the physical QD4 producer can move the full ~12.31 GB model through storage→pinned→CUDA in about **1.02 s** under favorable probe conditions.

C9 earlier showed QD4/32 MiB around **1.51 s** for the same full payload.

These were transport capability proofs, not complete ModelPatcher-ready production measurements.

### Forbidden UNET architectures

Do NOT use:

- CPU snapshot UNET weights,
- old full CPU-snapshot/two-lane activation,
- native second checkpoint read,
- FastSafe fallback inside Candidate A,
- duplicate full CPU state_dict materialization,
- second model-sized H2D,
- second model-sized CUDA representation,
- generic R42 staging/free-slot queue architecture,
- silent fallback to the normal loader.

### Required adoption proof

For the final model prove:

- 453/453 expected tensors,
- exact shapes,
- exact dtypes,
- CUDA device,
- same storage / `data_ptr` identity with QD views,
- correct NextDiT model,
- persistent QD owner retained long enough for the model.

Also instrument CUDA allocation:

- before skeleton,
- after skeleton,
- after QD destination,
- after `assign=True` adoption,

so a transient duplicate model-sized CUDA representation cannot hide behind final pointer identity.

### Fail closed

`_native_detection_input` or equivalent must not swallow arbitrary exceptions from quant/config conversion.

Unexpected conversion failure must be visible.

---

## 11. Sampler prepare

Purpose:

Execute only the exact lightweight graph dependencies needed before the sampler after Golden CLIP/UNET outputs are seeded.

Requirements:

- loader nodes must not reread models,
- heavy CLIP/UNET/VAE nodes must not execute,
- patcher identity must remain unchanged,
- no model-sized CUDA allocation,
- no hidden H2D.

### Known P1 bookkeeping bug

P1 originally counted the serial runner's entire cumulative execution history during sampler prepare and falsely treated earlier CLIPTextEncode execution as a new prep-stage execution.

That was corrected by taking a stage-local slice:

`runner.executed[executed_start:]`

Preserve that fix.

---

## 12. Sampling

Sampling is considered settled.

Do **not** launch another archaeology or mechanism-selection phase for the sampler unless new direct evidence proves a correctness problem.

Use current exact healthy sampler semantics.

Historical healthy sampler core is roughly **3.65–3.75 s**.

Some broader measurements near ~4.7–5.0 s include setup/transition differences and are not automatically equivalent.

### CacheDiT / sampler-internal behavior

Do not disable functionality intrinsic to the exact sampler merely because it is an optimization.

The seriality rule forbids moving heavy work across Golden stage boundaries; it does not forbid legitimate internal sampler behavior.

---

## 13. Sampler tail

Preserve the proven minimal/J1-style behavior where possible:

- avoid unnecessary post-sampler GC,
- do not perform broad cleanup,
- keep the transition into VAE explicit and small.

If exact historical J1 code cannot be recovered, use the simplest safe no-op/minimal transition and report it accurately.

Do not claim a sophisticated recovered tail when the implementation is only a placeholder.

---

## 14. VAE

### Selected mechanism

Use the **final R42-class file-backed QD VAE loader/binder**, but run it **serially after sampling**.

Do not reuse R42's historical overlap scheduling.

Desired structure:

```text
VAE descriptor/header
    ↓
file-backed QD transport
    ↓
direct bind/adoption
    ↓
VAE ready
    ↓
exact decode
```

Historical final-class component evidence was approximately:

- QD transport: ~0.09–0.10 s
- bind: ~0.03 s
- decode: ~0.38–0.44 s

Again, these are reference expectations, not permission to reconstruct totals from mismatched runs.

### Forbidden

- VAE model weights in CPU snapshot,
- hidden VAE preload under sampling,
- broken older R42 lifecycle that performs native fallback and later duplicates Golden QD work,
- duplicate native VAE load.

---

## 15. Output and durability

### Required semantic order

The output contract is:

```text
PNG encode
    ↓
atomic asset write INSIDE the mounted committed Modal Volume
    ↓
VOLUME_COMMIT_START
    ↓
VOLUME_COMMIT_COMPLETE
    ↓
reopen committed asset
    ↓
verify byte count
    ↓
verify SHA-256
    ↓
TRUE_FIRST_DURABLE_RESULT
    ↓
result assembly
```

A pre-commit result is not durable.

### Volume binding

The Golden contract must know both:

- actual Modal Volume handle,
- exact mount root on the filesystem.

Before durability can succeed prove:

`realpath(asset_abs_path)` is inside `realpath(volume_mount_root)`.

Fail closed on:

- path escape,
- mismatched mount,
- commit failure,
- reopened bytes mismatch,
- canonical output SHA mismatch.

### Canonical output

Expected exact PNG SHA-256:

`20b10e1f99831bc758d9df82f43ce0beb1cbc636a740d11a29eb2bffe90e5260`

### Result terminology

Keep these distinct:

- `OUTPUT_ENCODE_DONE`
- `ASSET_WRITE_DONE`
- `VOLUME_COMMIT_START`
- `VOLUME_COMMIT_COMPLETE`
- `TRUE_FIRST_DURABLE_RESULT`
- `RESULT_ASSEMBLED`
- actual remote return/yield
- client result received

Do not call a local result object "emitted".

---

## 16. Teardown

Golden runs use single-use minimal teardown.

Desired teardown:

- release QD pinned staging resources,
- verify Golden-owned worker threads are done,
- verify no required future is pending,
- persist telemetry,
- no full model unload,
- no giant GC,
- no `torch.cuda.empty_cache()`,
- no allocator purge,
- no model-sized CPU/GPU transfer.

Process exit owns final model/CUDA reclamation.

Historical controlled evidence showed full teardown could add ~2.56 s while minimal teardown was only a few milliseconds.

### Function timing rule

If `golden_teardown()` persists telemetry before returning, that persistence/fsync belongs inside the function headline wall.

Do not mark teardown END and then perform meaningful teardown work afterward.

---

## 17. Self-contained Golden module

Preferred canonical implementation file:

`comfymodal_runtime/golden_serial.py`

This file owns the ComfyModal-specific Golden logic, including as needed:

- Golden contracts/data structures,
- telemetry,
- QD reader machinery,
- storage-owner helpers,
- CLIP loader,
- CLIP forward,
- UNET loader,
- sampler handoff,
- VAE loader/decode,
- output/durability,
- teardown,
- one explicit `golden_serial_execute(...)`.

### Allowed imports

- Python stdlib,
- third-party packages,
- Torch,
- safetensors,
- PIL,
- Modal SDK,
- upstream ComfyUI modules/APIs,
- genuine external custom-node packages where the workflow requires them.

### Forbidden imports

The file must not import our old project implementation stack such as:

- `comfymodal_runtime.*` helpers,
- `comfyapp.py`,
- old profiler,
- old residency manager,
- old preload coordinator,
- old QD engine,
- old speculative loader infrastructure,
- old FastSafe helper stack.

If proven historical logic is needed, port the narrow relevant implementation into Golden rather than wrapping the old god file.

### Current P1 status

P1 substantially succeeded at the self-contained import boundary.

Do not throw away the entire file.

Repair the incorrect lifecycle/measurement contracts around the useful loader implementation.

---

## 18. Golden serial node runner

A narrow serial node driver is acceptable because the Golden pipeline must control exactly when nodes execute.

However, do not accidentally maintain a full homemade PromptExecutor.

### Golden-owned responsibilities

- exact serial scheduling,
- stage ownership,
- seeded Golden CLIP/UNET/VAE objects,
- no concurrent node scheduling,
- fail-closed unsupported workflow behavior.

### Prefer upstream ComfyUI for

- input normalization,
- hidden input semantics,
- V1/V3 return normalization,
- `NodeOutput`,
- lazy input semantics,
- execution result contracts,
- graph/link contracts,

where exact reusable upstream primitives exist.

### Frozen workflow principle

The Golden runner does not need to become a generic executor for arbitrary workflows.

Unsupported semantics can fail closed if the canonical workflow does not require them.

### Known V3 contract

Modern nodes may return `NodeOutput`-shaped objects containing:

- `.result`
- `.ui`
- `.expand`
- `.block_execution`

Normalize only according to actual installed upstream semantics.

Do not guess based on tuple behavior.

---

## 19. Function timing contract

The new Golden waterfall should be intentionally simple.

For every Golden function:

> **Primary duration = actual Python function entry -> actual function return/raise boundary.**

Child events can explain the function but cannot redefine the total.

Primary rows:

```text
actual_restore
golden_request_setup()
golden_clip_load()
golden_clip_forward()
golden_unet_load()
golden_sampler_prepare()
golden_vae_load()
golden_sampling()
golden_sampler_tail()
golden_vae_decode()
golden_output()
golden_durable_commit()
golden_teardown()
```

Also report separately:

```text
Python resume -> TRUE_FIRST_DURABLE_RESULT
TRUE_FIRST_DURABLE_RESULT -> actual remote return
actual remote return -> client receipt
command/submission -> Python resume
command -> client receipt
```

### Do not use old primary rows for Golden

These old concepts are not authoritative Golden headline metrics:

- PromptExecutor/cache setup,
- Pre-sampler execution,
- Sampler node to sampling,
- Post-sampling/VAE transition,
- mixed profiler-derived CLIP/sampler windows.

They may remain legacy diagnostics for non-Golden execution.

---

## 20. Structural invalidators

A run is **INVALID Golden evidence** if any of the following occurs:

### Snapshot invalidators

- CLIP/UNET/VAE model payload present in snapshot,
- QD owner present at capture,
- open checkpoint payload reader,
- model preload/prefetch worker survives capture,
- snapshot proof missing or incomplete.

### Identity invalidators

- wrong source/deployment hash,
- wrong snapshot/image ID,
- wrong canonical workflow,
- wrong model file,
- wrong GPU/profile when cohort identity is frozen.

### Execution invalidators

- fallback count > 0,
- second source read of a model payload,
- duplicate model-sized H2D,
- native loader runs after Golden load,
- forbidden cross-stage overlap,
- required worker/future pending at stage return,
- conditioning cache bypasses real CLIP forward,
- model payload comes from CPU snapshot,
- sampler uses a different UNET object than Golden published.

### Correctness invalidators

- output SHA mismatch,
- incomplete/partial model adoption,
- wrong dtype/shape/device/storage identity,
- commit failure,
- pre-commit durable stamp,
- committed-object reopen/hash failure.

### Cohort invalidators

For the final measured five:

- not `Fresh:YES`,
- warm-container reuse,
- source/config/snapshot changed between runs,
- hidden tuning between runs.

Invalid attempts must be preserved and reported separately.

Never silently drop them.

---

## 21. Telemetry and raw evidence

Raw artifacts outrank summarized profiler output.

For every structural/measured attempt preserve:

### Identity

- run/request ID,
- Modal task/input ID,
- instance/restored-container identity,
- snapshot ID,
- image ID,
- source/deployment hash,
- cloud/region/GPU,
- Torch/CUDA versions,
- CPU/memory request,
- Golden config/profile.

### Restore

- Python resume,
- restore start,
- restore end,
- method entry,
- restore duration.

### Golden functions

Exact entry/end wall for each function.

### Model stages

For CLIP/UNET/VAE capture as applicable:

- checkpoint path/hash/size,
- source bytes,
- source-read wall,
- QD configuration,
- device-ready timing,
- skeleton/constructor timing,
- bind/adoption timing,
- pointer/same-storage proof,
- owner identity,
- fallback count,
- duplicate read/H2D count.

### Output

- PNG encode,
- asset write,
- commit start,
- commit complete,
- reopen/hash,
- TRUE_FIRST_DURABLE,
- result assembly,
- actual remote return,
- client receipt.

### Teardown

Persist bounded teardown substage timing and worker/future checks.

---

## 22. ASCII Gantt

For every valid run generate a Python-side Golden Gantt using `█`, not `=`.

Example form:

```text
Restore         ██
Setup             █
CLIP load          ████
CLIP forward           ███
UNET                       ████
Sampler prep                  █
Sampling                       ███████████
Tail                                      █
VAE load                                   ██
VAE decode                                   ██
Output                                         █
Commit                                          █
Teardown                                         █
```

Use actual timestamps and scale.

Also generate dense internal detail for:

- CLIP load,
- UNET load,
- VAE load,

only when the child telemetry is directly measured.

---

## 23. Final five-run methodology

Do not begin the final cohort until the structural gate passes.

### Required flow

1. Finish implementation.
2. Run local/static validation.
3. Deploy the final candidate.
4. Record source/deployment/image/config identities.
5. Create a **runtime-only, model-free CPU snapshot**.
6. Prove snapshot contains zero CLIP/UNET/VAE payload.
7. Run **one post-snapshot structural canonical generation**.
8. If structural run fails:
   - diagnose,
   - fix,
   - redeploy,
   - recreate snapshot,
   - retry structural gate.
9. Once structural run passes:
   - **FREEZE source**
   - **FREEZE config**
   - **FREEZE snapshot**
10. Perform **five valid true-cold runs**:
    - `min_containers=0`
    - single-use
    - `Fresh:YES`
    - distinct fresh restored instance/container identities where possible
    - same deployment/snapshot/profile/GPU/workload
    - no conditioning-cache bypass of real encode
    - no source/config changes
11. Preserve invalid platform/request attempts separately and continue until exactly five VALID measured runs exist.
12. Do not remove slow valid runs.
13. Do not tune between the five.
14. Stop and report.

---

## 24. Statistics

For every primary function and important whole-path metric calculate:

- min,
- max,
- mean,
- median / p50,
- p90, with the chosen n=5 method stated,
- standard deviation,
- coefficient of variation,
- range.

Primary metric:

`remote Python resume -> TRUE_FIRST_DURABLE_RESULT`

Also summarize:

- restore,
- every Golden function,
- post-durable application tail,
- command->client result when host reconciliation exists.

No outlier deletion.

---

## 25. Current P1 conclusions

P1 is not useless.

It produced substantial valuable core code, especially:

- self-contained Golden module structure,
- QD transport ownership,
- direct CLIP/UNET/VAE implementation work,
- UNET Candidate A,
- explicit serial top-level architecture,
- same-storage validation,
- focused runner work.

However, P1 should not be treated as structurally complete.

Known defects include:

1. current Modal lifecycle still uses model-bearing CPU snapshot,
2. old production snapshot invariant expects UNET/VAE presence,
3. current `golden_restore()` is not actual restore,
4. snapshot proof was wired into teardown rather than pre-capture,
5. `RESULT_EMIT` was stamped before actual remote return,
6. function headline timings can exclude meaningful trailing work,
7. durability did not strongly bind output path to the Volume mount,
8. `ModelPatcherDynamic` detection/proof was incomplete,
9. UNET detection swallowed broad exceptions,
10. seriality reconciliation proved wrapper ordering more strongly than actual worker/future quiescence,
11. transient duplicate model-sized allocation needed stronger evidence,
12. GoldenSerialRunner risked becoming a partial PromptExecutor clone,
13. old waterfall remained misleading,
14. no valid Golden structural cohort existed.

P1 remote validation should therefore not be used as final Golden performance evidence.

---

## 26. P2 repair phase

P2 exists to repair the foundation before any more meaningful remote validation.

Three parallel lanes are intended.

### P2-1 — Golden core contract

Owns:

- `comfymodal_runtime/golden_serial.py`
- focused core tests.

Responsibilities:

- truthful function-wall timing,
- real restore-interface semantics,
- truthful result terminology,
- Volume mount binding,
- snapshot-proof helper cleanup,
- dynamic patcher detection,
- fail-closed UNET detection,
- stage quiescence,
- transient allocation evidence,
- narrow/upstream-backed serial runner.

No deployment.

### P2-2 — Modal lifecycle / snapshot adapter

Owns:

- `comfyapp.py`
- narrow Golden Modal adapter/config/lifecycle changes,
- focused adapter tests.

Responsibilities:

- eliminate model-weight snapshot for Golden,
- remove old snapshot model reuse for Golden,
- run proof at actual pre-capture,
- bridge real restore timestamps,
- thin adapter around `golden_serial_execute`,
- actual remote return timestamp,
- correct Volume mount forwarding,
- dynamic patcher runtime preflight,
- preserve non-Golden behavior.

No deployment.

### P2-3 — Golden observability / harness

Owns:

- Golden waterfall,
- benchmark/harness,
- validation/reporting,
- v2ctl/build isolation where needed,
- focused harness tests.

Responsibilities:

- Golden-native function table,
- exact function walls,
- correct durable/return/receipt boundaries,
- structural invalidation rules,
- ASCII Gantt,
- invalid-attempt preservation,
- five-run statistics,
- raw artifact handling,
- safe stable-source deployment preparation.

No deployment.

---

## 27. P3 integration phase

P3 is the single deployment/integration owner after P2 returns.

P3 is **not** a new architecture phase.

Its mission is to finish the original Golden experiment on the repaired foundation.

P3 should:

1. reconcile P2 changes,
2. resolve conflicts,
3. run complete local/static gates,
4. deploy from stable source,
5. create the runtime-only model-free snapshot,
6. run one structural generation,
7. fix structural failures if necessary,
8. redeploy/resnapshot until structural gate passes,
9. freeze source/config/snapshot,
10. execute five valid Fresh:YES runs,
11. produce the final evidence package.

### P3 may not

- casually switch CLIP/UNET/VAE candidates,
- introduce cross-stage overlap,
- move model weights into snapshot,
- tune between cohort runs,
- hide invalid attempts,
- call pre-commit results durable,
- optimize away required CLIP forward,
- weaken exactness.

If a chosen component is slow but structurally correct, report the measured truth first.

---

## 28. Safe concurrency / worktree rules

Other agents and Studio work may be active.

Agents must not:

- reset,
- revert,
- stash,
- clean,
- force-checkout,
- overwrite,
- delete,
- or otherwise destroy unfamiliar concurrent work.

Deployment/build mutation guards should remain enabled.

A recent Golden deploy was blocked because another Studio agent was modifying:

`tests/browser/fake/studio-fake-phase-i10-cross-tab-sync.spec.mjs`

The correct response is **not** to weaken the guard.

Use a stable isolated worktree or immutable prepared source tree for P3 deployment if needed.

One agent owns deployment at a time.

---

## 29. Testing philosophy

Tests are valuable when they prove meaningful contracts.

Prefer focused tests for:

- exact model adoption,
- stage ordering,
- worker/future quiescence,
- fail-closed invalid states,
- snapshot absence,
- durability ordering,
- exact output,
- telemetry semantics,
- adapter boundaries.

Avoid:

- test-count inflation,
- repetitive smoke tests,
- endless regression scaffolding for deleted behavior,
- tests that merely mirror implementation internals without protecting a real contract.

Passing tests do not replace real structural/runtime validation.

---

## 30. Final expected artifacts

The final integrated Golden effort should produce:

1. `comfymodal_runtime/golden_serial.py`
2. final Golden methodology/source/results Markdown report
3. five-run CSV
4. raw artifact/log directory containing every structural/cohort attempt
5. snapshot pre-capture proof
6. exact final source SHA-256
7. exact deployment/snapshot identities
8. per-run Golden telemetry JSON
9. per-run ASCII Gantt
10. complete invalid-attempt ledger

The final report must include enough provenance that a fresh engineer can independently audit every important conclusion.

Do not use ellipses in raw logs included as evidence.

---

## 31. Working performance budget

A reasonable conservative target composition is approximately:

| Stage | Working target |
|---|---:|
| Restore/setup | ~0.4–0.8 s |
| CLIP load | ~1.15 s |
| CLIP forward | ~1.1 s |
| UNET + handoff | ~1.0–1.6 s |
| Sampling + tail | ~3.7–4.9 s |
| VAE load + decode | ~0.48–0.60 s |
| Output/durability/exit | ~0.2–0.5 s |

This implies roughly **7.5–10.5 s** Python-side depending on tails.

Sub-10 remains plausible if:

- restore is healthy,
- CLIP forward is not pathological,
- UNET is near the intended <=1.5 s source-inclusive range,
- sampler is near the healthy regime,
- durability/teardown remain small.

These numbers are expectations only.

The actual Golden five-run cohort decides the truth.

---

## 32. Final rule

The Golden Path is successful only when the **actual assembled serial runtime** is:

- exact,
- file-backed for CLIP/UNET/VAE,
- model-free in snapshot,
- truthful in telemetry,
- serial in real work,
- durable before claiming durability,
- auditable from raw artifacts,
- and measured without hidden work.

**Optimize the real path. Measure complete functions. Preserve exactness. Keep the architecture simple.**
