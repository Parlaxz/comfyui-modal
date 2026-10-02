```text
# Batch RA1 Sampler / NextDiT Deep Decomposition and Repair — Explain the Entire ~6 Seconds

Use subagent-driven implementation and programming.

You are the ONE writer and ONE deployment owner for RA1.

Read-only subagents may aggressively inspect source, Git history, R0 artifacts, historical run reports, dependency history, ComfyUI, RES4LYF, CacheDiT, KJNodes, SageAttention, NextDiT, and previous diagnostics.

No other agent may edit/deploy concurrently with you.

Do not reset, stash, clean, revert, overwrite, or discard unrelated user work.

## Mission

Do NOT reduce this batch to:

"Is CacheDiT doing 10 computes / 7 skips?"

That is only one question.

The primary question is:

> What is the ENTIRE current ~5.7–6.3 second Golden sampling stage made of, why is it slower than the historical ~4.8–5.5 second proven-CacheDiT regime, and what source/backend/lifecycle change explains the difference?

We already have strong historical evidence that the sampler is dominated by the REAL NextDiT computes, not skip overhead.

RA1 must deeply reconstruct the sampler from source/history first, then use narrow runtime instrumentation only to settle the remaining unknowns.

If a correct narrow repair is proven, IMPLEMENT IT in RA1 and validate it.

Do not merely produce telemetry and stop.

## Starting state

Start from the completed R0 Golden source/control-plane state.

Read:

- `R0_FUTURE_AGENT_GOLDEN_OPS_CONTRACT.md`
- `R0_GOLDEN_OPERATIONS_HARDENING_REPORT.md`
- the installed `comfymodal-golden-ops` skill if available
- R0 deployment/run/gate/confirmation manifests
- all R0 raw remote evidence
- the RA1 read-only exploration report
- historical CacheDiT-positive/deep-sampling reports and logs

R0 proved:

- public Golden operations work;
- exact expected PNG SHA;
- five valid true-cold runs;
- source/runtime health;
- stable production untouched.

The R0 implementation remains mixed with pre-existing dirty worktree state.

Before editing:

1. inspect HEAD and working tree;
2. identify intentional R0 deploy-relevant changes;
3. identify unrelated pre-existing/user changes;
4. preserve both;
5. if safe, create a clean baseline commit containing ONLY intended R0 deploy-relevant changes;
6. never commit/reset/revert unrelated user work merely for cleanliness.

Deployment/source fingerprints remain authority.

## Public operations only

Use the R0 public interface.

Experimental app:

`batch-ra1-sampler-decomp`

Use:

python tools/v2ctl.py golden status --app batch-ra1-sampler-decomp

python tools/v2ctl.py doctor --profile golden_p1 --app batch-ra1-sampler-decomp

python tools/v2ctl.py golden deploy --app batch-ra1-sampler-decomp

python tools/v2ctl.py --profile golden_p1 --app batch-ra1-sampler-decomp source-probe

python tools/v2ctl.py golden run --app batch-ra1-sampler-decomp

Never call the legacy BAT deploy/run paths.

Never use generic `run_plan_stream`.

Never target production.

## Part A — reconstruct the current sampler BEFORE instrumenting

Trace the exact canonical Golden path from:

golden_sampler_prepare
→ RES4LYF/KSampler node
→ guider
→ sampler/solver
→ model application
→ CacheDiT wrapper
→ NextDiT
→ TRUE sampling completion
→ sampler tail

Determine from source and historical reports:

- exact 8-step solver semantics;
- why there are 17 model evaluations;
- which evaluations are genuine computes;
- which are CacheDiT returns;
- setup work;
- sampler/solver Python work;
- CFG/guider work;
- model-manager work;
- each real NextDiT forward;
- cache skip overhead;
- callback/progress work;
- teardown/tail work.

Do not reuse an old timing label without proving its boundaries.

In particular:

- the famous ~3.7-second number was a narrower historical sampling measure and is NOT automatically the full sampler comparator;
- historical deep profiles proving 17 calls / 10 computes / 7 skips and roughly ~4.8–5.5 seconds are the more appropriate full-stage evidence.

Reconstruct historical and current timing boundaries apples-to-apples.

Create an initial estimated decomposition BEFORE adding new runtime telemetry.

## Part B — deeply investigate the ~1 second apparent NextDiT compute regression

Treat this as a first-class investigation.

Strong historical evidence indicates most sampling time is the ten REAL NextDiT computes.

Investigate why their aggregate execution appears slower now.

Inspect relevant history/source/version changes including:

- NextDiT source;
- KJNodes;
- SageAttention integration;
- CacheDiT;
- ComfyUI attention dispatch;
- RES4LYF;
- Torch/CUDA;
- dtype/autocast policy;
- model ownership/device state;
- dynamic ModelPatcher behavior;
- attention kernel/backend selection;
- first-call kernel initialization;
- compiler/kernel caches;
- synchronization;
- model-management calls during sampling;
- any deterministic fallback path.

Do not stop at package version differences. Trace executable paths.

### High-priority Sage/attention hypothesis

Specifically inspect the current equivalent of:

- `PathchSageAttentionKJ`
- `sage_attention=auto`
- `_select_sage_runtime_mode()`
- any persisted Sage runtime-mode cache
- baked Sage kernel detection
- Triton fallback
- fallback to ComfyUI `attention_pytorch`
- provider/GPU-specific cached backend decisions

Determine the ACTUAL function/backend that each real NextDiT attention call executes.

A stable fallback from Sage to ordinary PyTorch attention is a high-priority hypothesis because it could:

- preserve exact output;
- slow all ten real computes;
- create a stable ~1-second aggregate regression.

Do not assume this is the answer. Prove or falsify it.

Also compare known historical runs showing Torch 2.13.0+cu130 can still achieve the older ~4.9-second full sampling regime, so do not lazily blame Torch 2.13 alone.

Rank root-cause hypotheses from strongest to weakest BEFORE making performance changes.

## Part C — CacheDiT truth

The read-only RA1 audit established that the old apparent 17-compute / 0-skip interpretation was not authoritative.

A cached forward can still enter the top-level transformer forward hook.

Therefore distinguish:

`model_forward_count`

from:

`cache_compute_count`.

For the canonical workflow establish:

total_model_calls = 17
cache_call_count = 17
cache_compute_count = 10
cache_skip_count = 7
cache_fallback_count = 0

Use the already-loaded actual CacheDiT module state.

Prove:

- optimizer input patcher identity;
- optimizer returned patcher identity;
- active Golden session patcher;
- actual `guider.model_patcher`;
- patcher passed to `prepare_sampling`;
- actual diffusion model;
- actual transformer;
- wrapper installation;
- cache activation;
- cache state reset;
- exact 17 per-call decisions;
- independent inner-block compute/skip classification;
- zero silent fallback.

If CacheDiT is already doing 10/7, DO NOT alter the predicate merely to make it "more optimized."

If it is not, locate the exact first broken edge and repair it.

Golden-required CacheDiT behavior must fail closed on silent cache fallback/identity mismatch/counter mismatch where practical.

Do not unnecessarily change non-Golden fallback semantics.

## Part D — minimum runtime decomposition needed

Only after source/history analysis, add the minimum diagnostics necessary to settle remaining questions.

Measure the COMPLETE sampling stage and reconcile it.

At minimum separate:

- sampler preparation;
- solver/guider non-model overhead;
- each of 17 model-call boundaries;
- real NextDiT compute vs cache skip;
- each of the ten real NextDiT forward durations;
- first real compute vs steady-state computes;
- cache skip duration;
- sampler tail/cleanup.

For the real NextDiT computes, identify the dominant internal categories from the ACTUAL model source.

Examples may include:

- attention;
- MLP/feed-forward;
- modulation/gating;
- residual operations;
- embeddings;
- normalization;
- output projection;
- other model-specific components.

Do not force these generic names if current NextDiT uses different boundaries.

Instrument the actual architecture.

Use CUDA events where GPU execution needs isolation, but:

- record on the active stream;
- do not `torch.cuda.synchronize()` around every block;
- reconcile events at an already-required later boundary;
- use CPU monotonic wall as authoritative enclosing stage time;
- never double-count nested CUDA time.

Target reconciliation:

absolute unexplained residual <= max(5 ms, 1% of the enclosing sampler wall)

If that cannot be achieved safely, report the residual explicitly rather than hiding it.

## Part E — implement the narrowest proven repair

If source/history plus the first valid runtime observation prove a specific regression, fix it.

Examples:

- wrong Sage/attention backend;
- stale persisted backend choice;
- unintended PyTorch attention fallback;
- wrong model ownership/device transition;
- unnecessary synchronization;
- real CacheDiT lifecycle break;
- another deterministic NextDiT execution regression.

Prefer fixing our code.

A narrow patch to pinned ComfyUI/KJNodes/CacheDiT is allowed when:

- the cause is understood;
- the patch is minimal;
- Golden exactness is preserved;
- failure is observable/fail-closed;
- tests cover it.

Do NOT:

- switch model precision casually;
- weaken exactness;
- change sampler/scheduler;
- change the CacheDiT decision predicate without proof;
- hide a slow path behind telemetry;
- call a different image "close enough."

If exactness fails, diagnose/redesign. Do not abandon a known-possible exact path.

## Part F — tests

Add focused tests for:

- true 17/10/7 arithmetic;
- top-level forward count != compute count;
- guider/patcher/transformer identity;
- cache fallback accounting;
- request-state reset;
- actual backend selection where testable;
- stale Sage/backend cache behavior if relevant;
- no diagnostic leakage;
- full-stage timing reconciliation logic;
- no change to non-Golden semantics unless intentional.

Do not inflate test counts.

Record exact commands/counts.

## Part G — deploy and 1+2 validation

Freeze deploy-relevant source.

Deploy `batch-ra1-sampler-decomp`.

Run source-probe/status/doctor.

Then collect exactly one eligible Golden observation.

IMPORTANT snapshot rule:

- request-time SNAPSHOT_CAPTURE = INVALID;
- the ONE directly subsequent experiment request = INVALID;
- later requests are eligible again;
- another capture re-arms the one-request guard;
- do NOT permanently taint the deployment;
- do NOT redeploy solely because capture occurred.

Retain every invalid attempt.

The first eligible RA1 observation must prove:

- exact expected PNG SHA;
- correct app/class/method;
- source identity;
- restore_count=1;
- request_count=1;
- true-cold identity;
- durability/reopen;
- strict seriality;
- correct Golden route;
- complete sampling decomposition;
- actual attention/backend identity;
- 17 calls;
- authoritative CacheDiT counters;
- zero silent fallback.

If the first eligible observation fails the RA1 gate:

DO NOT immediately run two more.

Diagnose and repair.

Redeploy only if deploy-relevant source changes.

Once the first eligible observation passes, collect TWO additional eligible valid observations separately.

Three accepted observations total.

No concurrency.

## Required report

Create:

`RA1_SAMPLER_NEXTDIT_DECOMPOSITION_AND_REPAIR_REPORT.md`

Include:

1. Executive conclusion.
2. Exact current sampler call graph.
3. Historical apples-to-apples sampling reconstruction.
4. Current ~6-second decomposition.
5. Ten-real-forward decomposition.
6. CacheDiT truth.
7. Actual Sage/attention backend truth.
8. Ranked root causes.
9. Source/history evidence.
10. Changes implemented and why.
11. Exact tests/counts.
12. Every remote attempt, including invalid snapshot-related attempts.
13. Three accepted observations.
14. Before/after timing table if a repair was implemented.
15. Raw logs in full or exact raw evidence paths.
16. Remaining unexplained residuals/questions.

Do not merely summarize logs. Preserve the complete evidence.

End with:

RA1_IMPLEMENTATION_COMPLETE=YES
RA1_ACCEPTED=YES/NO
CACHE_CALLS=<value>
CACHE_COMPUTES=<value>
CACHE_SKIPS=<value>
CACHE_FALLBACKS=<value>
ACTUAL_ATTENTION_BACKEND=<value>
SAMPLER_MEDIAN_MS=<value>
TEN_REAL_COMPUTES_MEDIAN_MS=<value>
EXPECTED_SHA_MATCH=YES/NO
VALID_RUNS=<value>
REPORT=RA1_SAMPLER_NEXTDIT_DECOMPOSITION_AND_REPAIR_REPORT.md
```

```text
# Batch RA2 Golden Snapshot + Restore Deep Reconstruction and Repair — Explain What Is Restored and What We Rebuild

Use subagent-driven implementation and programming.

You are the ONE writer and ONE deployment owner for RA2.

RA2 starts ONLY after RA1 is accepted.

If `RA1_ACCEPTED != YES`, stop. Do not build RA2 on a rejected RA1 state.

Keep all accepted RA1 changes.

Do not reset/stash/clean/revert unrelated user work.

## Mission

Do NOT frame this as:

"We don't know what is in the snapshot; instrument everything."

We intentionally control Golden snapshot construction.

The primary questions are:

1. What state does our code intentionally hand to Modal at the CPU snapshot boundary?
2. Does the actual process state agree with that model-free Golden contract?
3. What does Modal restore automatically?
4. What application work do WE unnecessarily redo after restore?
5. Why does restore sometimes exceed the <=3 second target?
6. Which post-restore work can be safely eliminated or skipped?

Instrumentation is confirmation.

Deep source/history reconstruction comes first.

## Starting state

Read:

- R0 contract/report/raw artifacts;
- RA1 report/raw artifacts;
- current accepted source;
- historical restore/snapshot reports;
- P3/P4 snapshot proofs;
- restore state probes;
- snapshot build/hygiene code;
- current R0 five-run/gate/confirmation artifacts.

Do not rely only on old P4-6 numbers.

Build a fresh restore-stage table from the CURRENT R0/RA1 lineage first.

R0 fixed:

`golden_runtime_state_volume_unavailable`

with a remote-safe lookup of already-mounted:

`comfymodal-runtime-config`

Preserve that fix.

## Experimental app

Use:

`batch-ra2-restore-truth`

Use only the R0 public Golden interface.

Never use production.

Never call legacy BAT deploy/run paths directly.

## Part A — prove the intended Golden snapshot from source

Trace the exact `snap=True` startup path.

Establish the positive Golden snapshot manifest FROM CODE.

The intended Golden capture should contain things such as:

- initialized Python interpreter/runtime;
- imported ComfyUI/custom-node modules;
- node/class registries;
- immutable runtime configuration;
- deployment/source generation identity;
- workflow/static topology or seed metadata intentionally retained;
- validation/proof metadata;
- quiescent coordinators;
- other intentional lightweight startup state.

And should NOT intentionally contain:

- CLIP weights;
- UNET weights;
- VAE weights;
- model patchers carrying those weights;
- QD CUDA owners;
- pinned H2D transport buffers;
- active source readers;
- active model-load workers;
- futures/tasks for request work;
- request IDs/output state;
- mutable request caches;
- CUDA context/driver state in the CPU snapshot path.

Trace the current equivalents of:

- `_clear_cpu_snapshot_state_for_golden()`
- `_golden_snapshot_proof_surfaces()`
- `_run_golden_snapshot_content_proof()`
- snapshot hygiene/quiescence
- Modal snapshot callback return

Do not merely quote function names.

Prove what each does.

## Part B — distinguish "snapshot contents" from RSS

Do not call the historical ~4.5–5 GB field serialized snapshot size.

It is resident-memory telemetry.

Modal's serialized snapshot byte count may remain unavailable.

What matters here is the physical resident process composition at capture.

Use cheap Linux memory evidence to characterize it:

- `/proc/self/smaps_rollup`;
- bounded top-N mappings;
- RSS;
- PSS;
- Private_Clean;
- Private_Dirty;
- Shared_Clean;
- Shared_Dirty;
- anonymous vs file-backed mappings where derivable.

Identify dominant mappings and categories.

Question:

> Is the ~4–5 GB resident process mostly imported runtime/shared libraries/file-backed clean pages, anonymous allocator state, accidental model/reference retention, or something else?

Do not conflate clean file-backed RSS with Modal serialized bytes.

## Part C — bounded hidden-reference audit

The existing direct-root proof may miss nested references.

Add or reuse a BOUNDED recursive selected-root census only where needed.

Inspect high-risk roots such as current equivalents of:

- runtime bootstrap/session state;
- legacy API bridges;
- preload bridge/coordinators;
- ComfyUI model-management loaded-model registries;
- object caches;
- actual-load futures;
- custom-node globals;
- node registries;
- closures/executors;
- snapshot seed/validation state.

Count identities/bytes without copying model contents.

For tensors:

- role;
- type;
- device;
- dtype;
- shape;
- numel;
- deduplicated underlying storage bytes;
- path to selected root.

Never:

- `.cpu()`;
- `.numpy()`;
- hash tensor contents;
- serialize object contents;
- run a universe-wide heap profiler;
- use unbounded `gc.get_referents()` exploration.

The point is to VERIFY the intentionally model-free contract, not rediscover Python's entire heap.

## Part D — ABSOLUTELY NO CUDA BEFORE CPU SNAPSHOT CAPTURE

This is non-negotiable.

In the `snap=True` CPU snapshot path do not introduce:

- `torch.cuda.is_available()`;
- current-device queries;
- device properties;
- capability calls;
- allocator probes;
- CUDA events;
- CUDA memory queries;
- anything else capable of initializing CUDA.

Use `/proc` and CPU-safe evidence only before capture.

If CUDA truth is needed, inspect it only at an appropriate post-restore boundary after normal CUDA initialization.

## Part E — reconstruct the CURRENT restore wall from raw evidence

The real performance question is not simply capture RSS.

Reconstruct:

remote Python resume
→ first restore line
→ ModalRuntimeEntrypoint.restore
→ RuntimeBootstrap.restore
→ generation/source checks
→ custom-node synchronization/reload
→ runtime-state Volume work
→ CUDA initialization
→ Sage/backend policy
→ model-management reconstruction
→ request-ready
→ Golden request setup

Use current R0/RA1 raw logs and code.

For every restore stage ask:

- Was this state restored by Modal?
- Are we validating it?
- Are we unnecessarily reconstructing it?
- Is a filesystem/Volume read genuinely required?
- Is a custom-node sync actually required when source generation matches?
- Are we doing work merely because old generic paths did it?
- Is the same generation/fingerprint already proven?
- Is there a fixed sleep/backoff?
- Is a reload unconditional when it can be safely skipped?
- Is work happening twice through two restore layers?

Specifically investigate all current equivalents of:

- `sync_custom_nodes`;
- generation reload;
- server Volume hydration;
- runtime-state reload;
- source fingerprint validation;
- dependency validation;
- CUDA initialization;
- restore GPU state;
- Sage policy;
- model reload;
- sleeps/retries.

Historical evidence showed custom-node synchronization could dominate restore by multiple seconds.

Do NOT assume that is still true.

Determine whether it remains true in CURRENT R0/RA1 evidence.

## Part F — restored-vs-reconstructed manifest

For each meaningful state item classify:

`RESTORED_UNCHANGED`
`RESTORED_THEN_VALIDATED`
`RESTORED_THEN_MUTATED`
`RECONSTRUCTED`
`RELOADED_FROM_VOLUME`
`RELOADED_FROM_FILESYSTEM`
`INTENTIONALLY_NEW_AFTER_RESTORE`
`UNKNOWN`

Use an immutable CPU-safe capture-generation nonce/fingerprint if needed to prove continuity.

Useful identity fields may include:

- deployment combined hash;
- custom-node generation;
- runtime generation;
- registry fingerprint;
- workflow/static topology hash;
- validation certificate;
- snapshot seed;
- capture nonce.

Do not use Python object IDs as the primary semantic identity.

## Part G — fix obvious application-owned restore waste

If code/history/current evidence proves work is unnecessary, FIX IT in RA2.

Likely categories include:

- redundant custom-node synchronization when generation already matches;
- redundant runtime-state reload;
- duplicate restore-layer work;
- unnecessary filesystem/Volume reads;
- fixed sleeps;
- unconditional reloads;
- checks that can use restored/frozen identity instead of reconstructing state.

Changes must be:

- fail-closed;
- source/generation/fingerprint guarded;
- observable;
- exactness preserving.

Do not skip a reload merely because it is slow.

Skip only when the current restored identity proves it unnecessary.

Preserve a safe slow path for mismatches/fallback.

Goal:

restore <= 3.0 seconds

If app-owned restore remains >3s, continue until you can explain the remaining wall precisely.

Do not blame "Modal scheduling" for time that occurs after Python resume.

## Part H — minimal telemetry

Only add telemetry needed to prove:

- capture composition;
- capture-generation continuity;
- restored-vs-reconstructed state;
- exact restore stage wall;
- skips vs reloads;
- diagnostic perturbation.

Measure diagnostic overhead.

Keep heavy raw mapping/census output in artifacts, not noisy normal stdout.

## Part I — tests

Add focused tests for:

- Golden snapshot positive/forbidden manifest;
- bounded recursive census;
- no CUDA calls in CPU capture diagnostics;
- capture nonce/fingerprint continuity;
- matching generation takes fast restore path;
- mismatch takes safe reload path;
- custom-node sync skip conditions;
- runtime-state fallback retained;
- no stale state leakage;
- restored/reconstructed classification;
- exact restore timing reconciliation.

Record exact commands/counts.

## Part J — deploy and 1+2 validation

Freeze deploy-relevant source.

Deploy:

`batch-ra2-restore-truth`

Run source-probe/status/doctor.

Collect one eligible valid Golden run.

Snapshot request rule:

CAPTURE = invalid
directly next request = invalid
later requests = eligible
new capture re-arms guard
NO permanent deployment taint
NO redeploy solely because capture occurred

The first eligible observation must prove:

- expected SHA;
- correct identity;
- valid snapshot proof;
- model-free capture contract;
- capture/restore identity evidence;
- complete restore decomposition;
- no unsafe CUDA-before-capture activity;
- durability/reopen;
- seriality;
- accepted RA1 sampler invariants.

If it fails, diagnose/rework before confirmation.

Once it passes, collect TWO additional eligible valid observations.

Three accepted total.

Report:

- raw restore times;
- mean;
- median;
- min;
- max;
- range;
- sample SD;
- CV.

## Required report

Create:

`RA2_SNAPSHOT_RESTORE_TRUTH_AND_REPAIR_REPORT.md`

Include:

1. Intended Golden snapshot manifest from source.
2. Physical capture-time memory composition.
3. Hidden/nested reference audit.
4. Proof of model-free capture or exact violations found.
5. Full current restore call graph.
6. Current restore timing decomposition.
7. Restored-vs-reconstructed table.
8. Custom-node/runtime-state synchronization analysis.
9. Application-owned waste discovered.
10. Changes implemented.
11. Before/after restore timing.
12. Tests and exact counts.
13. Every remote attempt.
14. Three accepted observations.
15. Raw evidence paths/full logs.
16. Remaining unavoidable/unknown Modal behavior.

End with:

RA2_IMPLEMENTATION_COMPLETE=YES
RA2_ACCEPTED=YES/NO
MODEL_FREE_SNAPSHOT_PROVED=YES/NO
CAPTURE_RSS_MEDIAN_BYTES=<value>
SERIALIZED_SNAPSHOT_BYTES=UNKNOWN/<only if genuinely known>
RESTORE_MEDIAN_MS=<value>
RESTORE_TARGET_LE_3000MS=YES/NO
DOMINANT_RESTORE_STAGE=<value>
EXPECTED_SHA_MATCH=YES/NO
VALID_RUNS=<value>
REPORT=RA2_SNAPSHOT_RESTORE_TRUTH_AND_REPAIR_REPORT.md
```

```text
# Batch RA3 CLIP Cold-Path Deep Decomposition and Repair — Explain Loader + Forward Separately

Use subagent-driven implementation and programming.

You are the ONE writer and ONE deployment owner for RA3.

RA3 starts ONLY after RA2 is accepted.

If `RA2_ACCEPTED != YES`, stop.

Keep the accepted RA1 and RA2 changes.

Do not reset/stash/clean/revert unrelated work.

## Mission

Do NOT reduce this batch to:

"Add timers and see whether CLIP is slow."

Deeply reconstruct the current CLIP path from source/history and the accepted R0/RA1/RA2 artifacts.

The questions are:

1. What is the current whole cold CLIP path actually costing?
2. How much is `golden_clip_load`?
3. How much is `golden_clip_forward`?
4. How do those compare apples-to-apples with the clean historical E37 path?
5. If there is a regression, is it:
   - source I/O;
   - QD/H2D;
   - model construction/bind;
   - model-manager/device preparation;
   - `encode_token_weights`;
   - transformer execution;
   - attention/backend;
   - casts;
   - synchronization;
   - post-processing?
6. Which part can be repaired now without broad transport rearchitecture?

Instrumentation confirms the few unknowns.

It does not replace source/history analysis.

## Starting evidence

Read:

- R0 report/raw evidence;
- accepted RA1 report/raw evidence;
- accepted RA2 report/raw evidence;
- RA3 read-only exploration;
- E37 clean-lane CLIP evidence;
- E29/E30/E31/E36/E37/R44F and other relevant CLIP reports;
- current Golden CLIP loader/forward source;
- ComfyUI CLIP/model-management source;
- current dependency/version history.

Important timing-boundary rule:

Historical ~1.110221 seconds was the inner `encode_token_weights` wall after CLIP was already GPU-ready.

It is NOT the whole cold CLIP stage.

The closest historical clean cold-conditioning comparison is approximately ~2.273–2.275 seconds.

Before claiming a regression, recompute CURRENT values from accepted R0/RA1/RA2 artifacts.

Do not blindly inherit an earlier ~3.9-second estimate if the current lineage differs.

## Experimental app

Use:

`batch-ra3-clip-decomp`

Use only the public R0 Golden control plane.

Never target production.

## Part A — current Golden CLIP call graph

Trace exact source:

Golden request
→ `golden_clip_load`
→ QD/source read
→ H2D
→ CUDA owner/storage
→ meta/device-safe CLIP construction
→ tensor adoption/bind
→ residency/storage proof
→ `golden_clip_forward`
→ CLIPTextEncode
→ tokenize
→ scheduled encode
→ encode_from_tokens
→ encode_token_weights
→ actual transformer
→ pooling/post processing
→ conditioning publication

Confirm the actual current functions rather than relying on historical names.

Golden should remain serial:

CLIP load
→ CLIP forward
→ UNET load

No historical CLIP/UNET overlap should be reintroduced just to chase a number.

## Part B — analyze `golden_clip_load`

Break loader wall into the ACTUAL current stages:

- source open/header/meta;
- source read;
- QD worker/service time;
- host staging if any;
- H2D;
- slot/event waiting;
- destination storage allocation;
- meta-model construction;
- state/tensor view construction;
- bind/adoption;
- validation;
- synchronization;
- residual.

Compare to the clean historical CLIP hydration/load boundary.

Trace current transport implementation and history.

Determine whether the slowdown comes from:

- Volume source throughput;
- QD coupling;
- block size/QD configuration;
- H2D serialization;
- construction/bind overhead;
- device-wide sync;
- duplicate validation;
- other deterministic work.

Do NOT launch another blind QD sweep.

Existing QD history is extensive.

Do not implement the broader R41 decoupled transport architecture here unless the CLIP evidence specifically proves a narrow CLIP-local version is necessary and safe.

Large transport architecture work belongs to the later RB transport lane.

RA3 should identify it clearly if that is the answer.

## Part C — analyze `golden_clip_forward`

Establish the exact current wall for:

T0 = CLIPTextEncode invocation start

A = tokenization

B = encode-time model-manager/device preparation

C = encode_token_weights

C1 = true transformer GPU span nested within C

D = post-transform conditioning construction

E = normalization/publication

T1 = CLIPTextEncode return

Required relationship:

T1 - T0 ≈ A + B + C + D + E + explicit residual

C1 is nested inside C and must NOT be added again.

Determine whether the active encode path performs ANY:

- `load_models_gpu`;
- model move;
- CPU→GPU transfer;
- dtype conversion;
- storage replacement;
- device synchronization;
- model-manager preparation.

Golden's loader proves physical CUDA residency.

That does not automatically prove every upstream ComfyUI logical ownership/model-manager path recognizes that residency.

Trace it.

## Part D — logical vs physical device truth

Record:

- logical load device;
- logical offload device;
- current device;
- physical parameter distribution;
- buffer devices;
- actual dtype;
- storage identities;
- patcher class/capabilities;
- any model-manager state relevant to loading.

If logical CPU metadata coexists with physically CUDA-resident parameters, determine whether it triggers unnecessary preparation.

Do not "fix" harmless metadata unless it actually causes work.

## Part E — transformer/backend truth

Determine the actual:

- transformer implementation;
- attention backend;
- autocast state;
- dtype behavior;
- first-call/warm behavior;
- hidden synchronization;
- hooks/wrappers.

Use paired CUDA events around the true transformer invocation if necessary.

Record on the active stream.

Do not add device-wide synchronize around every forward.

Reconcile at an existing required completion boundary.

## Part F — do not repeat already-rejected ideas without new evidence

Historical work already explored repeated BF16→FP32/cast-once behavior.

Do NOT resurrect cast-once merely because conversions exist.

Historical evidence found the benefit tiny relative to ~8 GB extra residency.

Only reopen it if current evidence proves the present path materially differs from that historical experiment.

Likewise, do not blame historical CLIP/UNET overlap when current Golden is serial unless you prove new background overlap exists.

Do not select an optimization from noisy whole-request time.

## Part G — source/history root-cause ranking

Before changing performance code, rank likely causes separately for:

### CLIP load regression

and:

### CLIP forward regression

For every hypothesis provide:

- supporting source/history evidence;
- contradicting evidence;
- what is already proven;
- what runtime evidence is still required.

Then add only the narrow instrumentation needed to choose between the top hypotheses.

## Part H — implement proven narrow repairs

If source + runtime evidence prove an avoidable regression, fix it.

Examples:

- redundant model-manager preparation;
- incorrect logical ownership causing load/move;
- unnecessary synchronization;
- accidental rematerialization;
- unnecessary construction/bind work;
- deterministic backend regression;
- duplicate load path.

Prefer our code.

A narrow guarded ComfyUI patch is allowed if necessary.

Preserve:

- exact output;
- strict Golden stage order;
- model/storage ownership;
- fail-closed behavior;
- no hidden fallback.

Do not reintroduce CLIP/UNET overlap.

Do not broadly redesign QD in this batch unless absolutely necessary.

## Part I — tests

Add focused tests for:

- already-resident CLIP does not rematerialize;
- physical storage identity;
- encode-time manager calls;
- timing bucket reconciliation;
- transformer CUDA-event accounting;
- logical/physical device distinction;
- no duplicate CLIP load;
- no hidden cross-stage overlap;
- any implemented root-cause repair;
- cleanup/no diagnostic leakage.

Record exact commands/counts.

## Part J — deploy and 1+2 validation

Freeze source.

Deploy:

`batch-ra3-clip-decomp`

Run source-probe/status/doctor.

Collect one eligible valid request.

Snapshot rule:

capture invalid
directly next invalid
later eligible
new capture re-arms guard
no permanent taint
no capture-only redeploy

First eligible run must prove:

- expected SHA;
- correct source/app/class/method;
- restore/request true-cold identity;
- durability/reopen;
- seriality;
- accepted RA1 CacheDiT/sampler invariants;
- accepted RA2 snapshot/restore invariants;
- complete CLIP load decomposition;
- complete CLIP forward decomposition;
- timing reconciliation;
- no unexpected load/move/fallback.

If it fails, repair before confirmation.

Once accepted, collect TWO more eligible valid observations.

Three accepted total.

For each report:

- `golden_clip_load`;
- `golden_clip_forward`;
- combined cold CLIP path;
- `encode_token_weights`;
- true transformer span;
- manager/device prep;
- source read/H2D;
- residual.

Report raw, mean, median, min, max, range, sample SD, CV.

Compare apples-to-apples against historical E37 boundaries.

## Required report

Create:

`RA3_CLIP_COLD_PATH_DECOMPOSITION_AND_REPAIR_REPORT.md`

Include:

1. Executive verdict.
2. Current exact CLIP call graph.
3. Historical timing-boundary normalization.
4. Current loader decomposition.
5. Current forward decomposition.
6. Logical vs physical device truth.
7. Model-manager truth.
8. Transformer/backend truth.
9. Ranked loader root causes.
10. Ranked forward root causes.
11. Implemented repairs.
12. Rejected/reopened historical ideas and why.
13. Tests/counts.
14. Every remote attempt.
15. Three accepted observations.
16. Before/after comparisons.
17. Full raw evidence paths/logs.
18. Remaining opportunities explicitly deferred to RB/R3.

End with:

RA3_IMPLEMENTATION_COMPLETE=YES
RA3_ACCEPTED=YES/NO
CLIP_LOAD_MEDIAN_MS=<value>
CLIP_FORWARD_MEDIAN_MS=<value>
CLIP_COLD_TOTAL_MEDIAN_MS=<value>
ENCODE_TOKEN_WEIGHTS_MEDIAN_MS=<value>
TRANSFORMER_MEDIAN_MS=<value>
ENCODE_TIME_MODEL_MANAGER_WORK=<value>
EXPECTED_SHA_MATCH=YES/NO
VALID_RUNS=<value>
REPORT=RA3_CLIP_COLD_PATH_DECOMPOSITION_AND_REPAIR_REPORT.md
```
