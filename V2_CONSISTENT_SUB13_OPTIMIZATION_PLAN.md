# V2 Consistent Sub-13 Optimization Plan

**Status:** Replacement for `V2_SUB15_SEQUENTIAL_OPTIMIZATION_GUIDE(2).md`  
**Scope:** Production V2 true-cold command-to-response performance  
**Starting point:** The validated Step 3 cold-cache-parity commit, once the Step 3 agent has completed validation and committed it  
**Target hardware:** NVIDIA RTX PRO 6000 Blackwell Server Edition  
**Target runtime policy:** `min_containers=0`, `scaledown_window=4`  
**Primary target:** Three consecutive verified true-cold requests below 13.0 seconds, with a median at or below 12.5 seconds  
**Secondary target:** Eliminate the 24–27-second application-side outliers without using warm containers

---

## 1. Executive decision

The old roadmap was built around an earlier assumption that first-request graph/cache construction was the dominant cold-only penalty. The validated recent runs show that this is no longer true.

The dominant remaining opportunities are:

1. **UNET CPU-state readiness and GPU activation**
   - Healthy cold activation: approximately `2.02–2.35s`.
   - Observed outlier for the same approximately `12.4GB` UNET: approximately `7.61s`.
   - Warm post-pass activation: approximately `0.03–0.05s`.
   - This is both a large median opportunity and the largest consistency risk.

2. **CLIP model readiness and first cold encode**
   - Recent graph-visible cold CLIP: approximately `2.49–3.46s`.
   - Complete cold prefill can exceed `4.0s`.
   - Post-full-pass warm CLIP node execution: approximately `0.277s`.
   - Exact conditioning prefill is already single-flight and graph consumption is already using it. The remaining work is mostly model/page/device readiness, not adding another conditioning future.

3. **First-pass sampler parity**
   - Recent cold sampling: approximately `4.93–4.98s`.
   - Post-full-pass warm sampling: approximately `4.19s`.
   - Historical healthy BF16 + CacheDiT sampling: approximately `3.69–3.73s`.
   - The known fast path must be recovered and enforced before speculative sampler redesign.

The new plan therefore prioritizes those three gaps first. The old Step 4 local-handle work, VAE snapshotting, certificate caching, output transport, and ownership trimming remain useful, but they are supporting wins rather than the primary route to sub-13.

Persistent cross-container conditioning caching remains **last**, as explicitly required. It is a hit-only product optimization and must not be used to conceal an unresolved universal cold path.

---

## 2. Immutable production constraints

Every phase must preserve:

```text
min_containers=0
scaledown_window=4
production RTX PRO 6000
production workflow and source workflow
eight sampler steps
current sampler and scheduler semantics
current image dimensions
current CFG and denoise semantics
BF16 UNET construction and compute
manual_cast_dtype absent/None
CacheDiT enabled on the intended production path
SageAttention/RES4LYF behavior
exact output metadata and image behavior
```

Never use:

```text
GPU memory snapshots
warm containers
keep-warm pings
scheduled warmups
longer scaledown windows
dummy image generations
unbounded background workers
a second model-loading framework
a second GPU/model mutation lock
```

The CPU memory snapshot must continue to retain the canonical CLIP and UNET objects unless a later measured ownership change preserves the same no-file-read cold behavior.

---

## 3. Evidence baseline

### 3.1 Recent healthy true-cold totals

```text
18.598s
19.411s
19.116s
19.371s
```

Derived summary:

```text
median command-to-response: approximately 19.24s
median Modal platform/host interval: approximately 4.95s
median remote app-controlled path: approximately 13.69s
```

### 3.2 Typical recent application stages

```text
application restore:             0.54–1.17s
remote setup:                    0.25–0.40s typical
PromptExecutor/cache:            0.29–0.49s
first node to CLIP:              0.25–0.62s
CLIP to sampler node:            3.08–3.56s
sampler node to sampling:        2.15–2.43s
sampling:                        4.93–4.97s
post-sampling transition:        0.52–0.59s
VAE decode:                      0.41–0.43s
output persistence:              0.22–0.24s
```

### 3.3 Post-full-pass warm lower bound

The warm example was not a valid cold request. A prior image had already completed on the same container. It nevertheless proves what the same workflow can do after model pages, GPU residency, allocators, kernels, and ComfyUI state have all been exercised.

```text
PromptExecutor/cache:            approximately 0.156s
complete pre-sampler:            approximately 0.691s
CLIP node execution:             approximately 0.277s
UNET activation/load:            approximately 0.032s
sampling:                        approximately 4.194s
post-entry application path:     approximately 5.9–6.0s
```

This is a lower-bound state, not a target to reproduce through GPU snapshotting.

### 3.4 Critical outlier evidence

The same approximately `12.4GB` UNET allocation took:

```text
healthy cold: approximately 2.02s
outlier cold: approximately 7.61s
```

During the outlier:

```text
same underlying diffusion model identity: yes
one registered UNET GPU load: yes
Torch intra-op/inter-op: 16/32
peak effective cores: approximately 16.05
time above 19 cores: 0ms
sampling: approximately 4.98s, unchanged
application restore: approximately 1.00s, unchanged
```

The outlier was therefore not caused by the old broad 20–32-core CPU plateau and was not a sampler regression. It was concentrated inside making the exact same UNET GPU-ready.

### 3.5 Current architecture already available

The repository already contains:

```text
ModelPreloadCoordinator
V2LoaderBridge
one shared model/GPU mutation lane
single-flight model futures
single-flight exact CLIP prefill
SnapshotExecutionSeed
PreSamplerCache
CPU snapshot model identities
page-fault tracking
deduplicated storage-registry/residency support
UNET forward probes
waterfall and critical-path instrumentation
```

The plan must extend those structures. It must not build parallel replacements.

---

## 4. Sub-13 target budget

To remain below 13 seconds even when the Modal platform interval approaches 6 seconds, the production target should be:

| Non-overlapping stage | Target |
|---|---:|
| Local preparation and cached Modal handle | `<=0.05s` |
| Modal scheduling/host snapshot resume | `<=5.30s` median; tolerate approximately `6.0s` |
| Application restore and restore-to-method | `<=0.75s` |
| Method setup, Step 3 seed, executor, first-node setup | `<=0.45s` |
| Graph-visible CLIP path | `<=0.65s` |
| Graph-visible UNET wait | `<=0.35s` |
| Sampling | `<=3.85s` |
| Post-sampling, VAE, output, and return | `<=0.85s` |
| **Total with 5.30s platform** | **`<=12.25s`** |
| **Total with 6.00s platform** | **`<=12.95s`** |

This budget is demanding but grounded in already observed states:

- CLIP has run at approximately `0.277s` after one full pass.
- UNET demand has fallen to approximately `0.03–0.05s` when already resident.
- Sampling has historically run at approximately `3.69–3.73s`.
- Restore has already reached approximately `0.54–0.65s`.
- The warm post-entry application path was approximately six seconds.

The plan does **not** require every stage to equal its warm minimum. It requires the expensive cold preparation to occur earlier, more consistently, or outside the visible critical path.

---

## 5. Priority order and expected gains

The table is ordered by implementation priority, dependency, and measured universal cold-path opportunity.

| Priority | Workstream | Universal cold gain | Tail gain | Difficulty | Main risk |
|---:|---|---:|---:|---|---|
| 1 | UNET readiness, transfer consistency, and safe earlier activation | `1.5–2.2s` | up to `5.5s+` | High | CLIP/page/PCIe contention |
| 2 | CLIP model/page/device readiness | `1.5–2.7s` | `1–3s` | High | Competing with UNET and restore pager |
| 3 | Recover BF16 + CacheDiT first-pass sampler parity | `0.7–1.2s` | `0.7–1.2s` | Medium-high | State-changing warmup or stale compiled caches |
| 4 | Combined bounded CLIP/UNET overlap | `0.3–1.2s` incremental | variance reduction | High | Two slower tasks instead of useful overlap |
| 5 | Certificate/static-runtime snapshot package | `0.15–0.9s` | `0.8s` | Low-medium | Stale certificate acceptance |
| 6 | Persistent local Modal handle and profile state | `0.35–0.52s` on a miss | local variance | Low-medium | Stale deployment handle |
| 7 | Snapshot and seed VAE; optionally prepare VAE late during sampling | `0.15–0.45s` | `0.3s` | Medium | Larger snapshot/platform regression |
| 8 | Output and return transport | `0.1–0.6s` on current evidence | product latency | Medium | Metadata or compatibility regression |
| 9 | Snapshot ownership and memory-layout trimming | `0–0.3s` median | `0.2–0.8s` | High | Accidental model reload or identity break |
| 10 | Persistent exact-conditioning cache | `2.5–3.5s` on a hit only | repeated-prompt UX | High | Privacy, invalidation, stale tensors |

The conditioning cache has a large hit-only gain but remains last because it does not improve unique-prompt cold requests and would obscure whether the universal path is actually solved.

---

# PHASE 0 — Finish Step 3 and freeze the production baseline

## Objective

Begin only from the validated and committed Step 3 implementation.

Do not use:

```text
a dirty Step 3 tree
the temporary diagnostic worktree
an unstable unvalidated commit
a deployment containing temporary sub-13 probes
```

## Required baseline

After Step 3 is committed:

1. Deploy through the supported batch path.
2. Run three verified true-cold production-profile requests.
3. Use low-overhead instrumentation only.
4. Record every run, including platform outliers.
5. Confirm:
   - one CLIP encode;
   - one UNET transfer;
   - one CacheDiT attachment;
   - exact retained object identity;
   - Step 3 seed applied;
   - no hidden request-owned future;
   - complete waterfall reconciliation.

## Gate

Step 3 is considered the base when:

```text
exec_start_to_cached <= immediate-warm +100ms
structural pre-sampler <= immediate-warm +250ms or within 10%
application restore does not regress by more than 100ms
no time is shifted into restore or a background future
```

No later phase may compensate for a failed Step 3 implementation.

---

# PHASE 1 — Make UNET readiness and GPU activation fast and consistent

## Why this is first

This is the largest consistency risk and one of the largest median wins.

The same object and same approximately `12.4GB` allocation have taken both approximately `2.02s` and `7.61s`. Starting the operation earlier without understanding that variance could turn CLIP’s three-second cost into an eight-second cost through contention.

Therefore this phase has two parts:

```text
1A. Attribute the slow path precisely.
1B. Implement the smallest correction that matches the measured cause.
```

## 1A. One bounded deep attribution request

Do not run another broad matrix.

Run at most **one genuine deep true-cold request** before implementation, unless the run fails to activate deep mode.

Before continuing past request entry, require markers equivalent to:

```text
diagnostic_mode=deep
latency_valid=false
storage_registry role=UNET
storage_residency role=UNET
```

The request must capture:

```text
UNET resident bytes/pages before activation
minor and major page-fault deltas
mapping type and NUMA distribution
ModelPatcher.load total
tensor enumeration/list preparation
patch application
cast preparation
actual CPU-to-GPU copy interval
CUDA-event transfer duration where valid
CUDA synchronization interval
bytes allocated/transferred
ComfyUI loaded-model cache publication
CacheDiT/Sage preparation
process and thread CPU
GPU utilization
memory-controller utilization
PCIe throughput when available
```

Do not run thread A/B, `madvise`, full overlap, or multiple schedule modes during this attribution request.

## 1B. Branch according to measured cause

### Case A — Restored-page demand dominates

Symptoms:

```text
low starting residency
large minor-fault growth
wall time substantially exceeds CPU time
H2D event time is much smaller than total ModelPatcher.load
```

Candidate implementation:

- Cache an ordered, deduplicated UNET storage registry in the CPU snapshot.
- Begin **bounded read-only page readiness** after exact request/deployment identity is validated.
- Use one worker.
- Prefer kernel-supported advice or a native/vectorized page-read path.
- Do not walk tensor elements in Python.
- Do not pre-touch all models concurrently.
- Do not begin before Modal restore has returned unless a measured experiment proves that the pager benefits rather than regresses.

### Case B — Python/tensor traversal dominates

Symptoms:

```text
resident pages already high
process CPU approximately equals wall time
many repeated tensor/model patch scans
H2D event duration much smaller than total load
```

Candidate implementation:

- Snapshot the immutable ordered tensor/copy plan.
- Cache static patch metadata and exact target-device/dtype decisions.
- Avoid repeated parameter enumeration, static patch hashing, and device-policy reconstruction.
- Preserve one canonical ModelPatcher and the same underlying diffusion object.
- Never cache request-dependent mutable patch results.

### Case C — H2D/copy engine dominates

Symptoms:

```text
resident pages high
CUDA-event copy time approximately equals load wall
low Python overhead
low fault growth
```

Candidate implementation:

- Test a dedicated CUDA copy stream with one terminal event joined at sampler demand.
- Remove premature full-device synchronization where correctness allows an event wait.
- Test batched/ordered copies only when supported by the real model layout.
- Test pinned staging only for a bounded subset and only after memory/RSS risk is quantified.
- Never pin the full 12.4GB model by default.

### Case D — Synchronization/cache publication dominates

Symptoms:

```text
copy event ends early
load_models_gpu remains blocked
long synchronization or model-cache publication interval
```

Candidate implementation:

- Replace global synchronization with the narrow event dependency required by the consumer.
- Minimize work under the mutation lane.
- Publish cache identity only after the exact transfer event is complete.
- Keep model-manager mutation serialized.

## Safe scheduling experiment

After the underlying variance source is corrected, test only these modes:

```text
A. current late sampler-demand activation
B. UNET page readiness begins at request entry, GPU activation begins at CLIP encode start
C. UNET page readiness and activation begin after CLIP model readiness but before encode completion
```

Do **not** begin with unrestricted request-entry H2D.

Use:

```text
one exact UNET future
one physical transfer
one mutation lane
one underlying diffusion object
one CacheDiT attachment
```

## Acceptance

For three verified true-cold requests:

```text
UNET activation median <=2.20s
UNET activation worst <=2.50s
graph-visible sampler-to-sampling wait <=0.50s median
no run above 3.0s
one physical model-sized allocation
CLIP wall regression <=0.25s
restore regression <=0.10s
sampling regression <=0.10s
time above 19 effective cores does not materially increase
no request-owned activation future after response
```

A scheduling candidate must improve command-to-response median by at least `250ms`; otherwise keep the safer order.

## Expected result

```text
median saving: 1.5–2.2s
tail saving: up to 5.5s or more
```

---

# PHASE 2 — Reduce cold CLIP readiness and exact encode cost

## Why this is second

The exact CLIP prefill already exists and is single-flight:

```text
one prefill encode
zero duplicate graph encode
graph consumes prepared result
```

Adding another future is not the solution.

The remaining target is:

```text
restored CLIP CPU-page readiness
ComfyUI model-manager readiness
CLIP GPU activation
kernel/allocator readiness
actual transformer encode
```

## Required decomposition

Measure separately:

```text
prefill schedule-to-worker-start
CLIP storage residency before first use
CLIP model-manager lookup
CLIP GPU activation/H2D
tokenization
positive/negative encode
actual transformer forward
conditioning object construction
future completion
graph demand
graph wait
```

## Implementation priorities

### A. Start request-independent CLIP readiness earlier

After validating:

```text
workflow
deployment
custom-node generation
exact CLIP identity
device policy
```

begin CLIP model readiness immediately.

The exact prompt encode begins as soon as the prompt bundle is available and joins the same prepared CLIP object.

### B. Reuse snapshot-safe static work

Snapshot or cache:

```text
tokenizer object and configuration
exact loader output identity
CLIP type/device policy
ordered storage registry
static model-manager metadata
safe graph-role mapping for positive/negative conditioning
```

Do not snapshot conditioning tensors for arbitrary prompts.

### C. Page readiness only when evidence supports it

If cold CLIP begins with low residency and high fault growth:

- use one bounded CLIP readiness worker;
- avoid simultaneous full UNET page touching;
- measure Modal pager, host memory, and VAE Volume-read overlap;
- retain the candidate only when total wall improves.

### D. Thread topology A/B, bounded

The post-full-pass warm example reported `16/16`; recent cold runs reported `16/32`.

Run this experiment only after the setting is proven to apply before Torch parallel work:

```text
current production topology
16 intra-op / 16 inter-op
```

Use one establishment request per mode. Run three final requests only for a candidate that improves the first comparison.

Do not assume thread topology is the cause: the 7.61-second UNET outlier occurred under the same 16/32 topology as healthy runs.

## Acceptance

For three verified true-cold requests:

```text
one exact CLIP encode
zero duplicate graph encode
total exact prefill <=1.50s median
graph-visible CLIP path <=0.80s median
graph-visible CLIP path <=1.00s worst
conditioning output structurally equivalent
no UNET activation regression >0.25s
no sampling regression
no persistent prompt/conditioning cache
```

## Expected result

```text
median saving: 1.5–2.7s
```

---

# PHASE 3 — Recover and enforce the known 3.7–4.0-second sampler

## Objective

Turn the known BF16 + CacheDiT sampler path back into a production invariant.

Do not redesign the sampler until the known path is fully compared.

## Required invariants

```text
native BF16 UNET
BF16 compute
manual_cast_dtype absent/None
same underlying diffusion object from snapshot to first forward
CacheDiT attached exactly once
SageAttention intended path active
eight sampler steps
same sampler/scheduler/CFG/denoise
no model-sized load during sampling
```

## First-pass decomposition

Record:

```text
sampling wrapper entry
first UNET forward entry/exit
first two sampler-step durations
all eight step durations
CacheDiT decision per step
SageAttention first-use interval
FeatureInjLatent/RES4LYF intervals
CUDA allocator growth/retries
Triton/Torch-extension cache evidence
GPU clock and utilization
```

## Candidate fixes

In priority order:

1. Repair any BF16/CacheDiT invariant mismatch.
2. Pre-import CacheDiT, Diffusers, Transformers, and attention modules in the image/snapshot.
3. Ensure compiled Triton/Torch-extension artifacts are built into the immutable image and keyed to:
   - GPU compute capability;
   - CUDA version;
   - Torch version;
   - custom-node generation;
   - model code identity.
4. Initialize generic CUDA libraries/streams/handles without running a dummy model generation.
5. Remove repeated first-call static analysis or wrapper construction.
6. Reduce allocator growth only if allocation traces show it is material.

Do not run a dummy full UNET forward merely to warm the container. Such a forward can mutate CacheDiT state, allocator state, or model caches and would be equivalent to hiding a warmup request inside production execution.

## Acceptance

```text
sampling median <=4.00s
sampling worst <=4.10s
target preferred median 3.70–3.90s
no output difference
no extra restore work >0.10s
no hidden model forward before the real sample
no model-sized transfer inside sampling
```

## Expected result

```text
median saving: 0.7–1.2s
```

---

# PHASE 4 — Select the combined CLIP/UNET schedule

## Dependency

Do not begin until:

```text
UNET activation is stable
CLIP readiness is independently improved
sampler path is stable
```

Otherwise the experiment cannot distinguish useful overlap from two contending slow operations.

## Scheduling candidates

### Mode 1 — CLIP-first deterministic

```text
CLIP readiness
exact encode
UNET activation
sampler
```

### Mode 2 — Parallel page readiness, serialized GPU mutation

```text
CLIP page readiness ─────┐
                         ├─ CLIP GPU readiness and encode
UNET page readiness ─────┘
                         └─ UNET GPU activation through mutation lane
```

### Mode 3 — CLIP compute overlapped with UNET H2D

```text
CLIP model ready
CLIP transformer encode starts
UNET activation enters copy phase on a controlled stream
graph joins both terminal events
```

### Mode 4 — Full request-entry overlap

Test only when the earlier modes show that:

```text
page faults do not compete
CLIP does not materially slow
UNET copy does not materially slow
model-manager mutation remains serialized
```

## Required measurements

```text
CLIP interval
UNET interval
actual overlap
sequential-equivalent duration
combined duration
overlap efficiency
CLIP slowdown
UNET slowdown
fault overlap
VAE read overlap
effective CPU cores
time above 16/19/20 cores
GPU utilization
memory-controller utilization
PCIe throughput
mutation-lane wait
graph wait
command-to-response
app-controlled total
```

## Paid-run discipline

- One candidate request per mode.
- Reject immediately if it loses or violates safety.
- Run three final cold requests only for the best surviving mode.
- Maximum five paid requests for the entire phase without explicit user approval.

## Acceptance

```text
>=250ms median command-to-response improvement
worst-of-three does not regress >250ms
CLIP slowdown <=250ms
UNET slowdown <=250ms
one CLIP encode
one UNET transfer
one mutation-lane owner
no deadlock, OOM, fallback duplication, or output mismatch
```

## Expected result

```text
incremental saving after Phases 1–3: 0.3–1.2s
```

---

# PARALLEL SAFE TRACK A — Snapshot certificate and static runtime package

This track can be investigated in parallel with the model work because it does not require changing CLIP/UNET scheduling.

## Evidence

Recent certificate work has ranged from approximately:

```text
0.15s
to
0.90s
```

## Snapshot-safe package

Retain:

```text
certificate contents
certificate identity/schema
workflow hash
source workflow hash
custom-node generation
deployment combined hash
production registry
output-node IDs
Step 3 execution seed
sampler static metadata
loader output identities
```

At request time:

1. Validate all identities.
2. Use the snapshotted package on an exact match.
3. Fall back to direct mounted-file read on any mismatch.
4. Use `volume.reload()` only when coherence requires it.
5. Never silently accept stale certificate contents.

## Acceptance

```text
certificate hit <=25ms
remote method setup <=0.20s preferred
fallback correctness preserved
no stale certificate acceptance
no restore increase >0.05s
```

## Expected result

```text
0.15–0.9s depending on current cache state
```

---

# PARALLEL SAFE TRACK B — Persistent local Modal handle reuse

## Objective

Reuse within the persistent ComfyUI process:

```text
Modal client
class lookup
class instance handle
active-profile result
deployment identity
```

Key and invalidate by:

```text
workspace/environment
app name
class name
deployment image/generation
method
```

On a stale-handle or deployment-not-found error:

1. invalidate exactly once;
2. rebuild;
3. retry once;
4. do not loop.

## Acceptance

```text
steady-state handle lookup <=20ms
no repeated cls.from_name
no repeated class instance construction
no cross-deployment stale handle
```

## Expected result

```text
0.35–0.52s on current local misses
near zero when already cached
```

---

# PARALLEL SAFE TRACK C — Snapshot and seed VAE

## Objective

Eliminate the first-request VAE Volume read and construction without increasing platform time more than it saves.

## Implementation

- Construct one canonical VAE during CPU snapshot creation.
- Add its exact role identity.
- Retain one canonical loader output.
- Seed `VAELoader` through the existing bridge pattern.
- Preserve normal loader fallback on mismatch.
- Do not keep duplicate state dictionaries or construction temporaries.

Optional later experiment:

- Begin VAE GPU readiness during the last sampler steps.
- Use the existing mutation lane.
- Retain only if GPU contention does not slow sampling.

## Risk

The VAE is approximately `320MB`, so adding it to the snapshot can slightly increase host snapshot restore cost. Judge net command-to-response, not the VAE timer alone.

## Acceptance

```text
zero VAE model-file read on exact snapshot hit
one canonical VAE object
same decode output
net total-wall improvement >=100ms
platform/restore regression smaller than saved VAE work
```

## Expected result

```text
0.15–0.45s
```

---

# PHASE 5 — Output and return transport

## Objective

Minimize the tail without changing metadata or user-visible behavior.

Measure separately:

```text
VAE decode
tensor-to-image conversion
image encoding
metadata embedding
Volume write
Volume commit
response serialization
base64 encoding
remote transfer
local base64 decode
local file write
benchmark artifact formatting
```

## Candidates

1. Return a durable asset/path plus structured metadata instead of duplicating the full image as base64 when the caller supports it.
2. Avoid encoding the same image twice for autosave and response.
3. Stream or directly transfer binary bytes where Modal and the plugin API safely support it.
4. Move benchmark formatting after the measured response boundary.
5. Cache immutable metadata templates, not image bytes.

## Acceptance

```text
identical image bytes or accepted deterministic equivalence
identical embedded metadata
no lost autosave
no second image encode
tail <=0.85s combined with VAE
```

## Expected result

```text
0.1–0.6s on latest evidence
larger only if local/base64 time is currently outside the waterfall
```

---

# PHASE 6 — Snapshot ownership, storage layout, and restore pressure

## Objective

Reduce restore variance and page pressure without removing CLIP or UNET and without forcing file reloads.

## Ownership census

Inspect:

```text
canonical CLIP
canonical UNET ModelPatcher
underlying diffusion model
canonical VAE
snapshot loader outputs
loader bridge
preload coordinator
completed future results
runtime bootstrap
Step 3 seed
certificate/registry
ModelPatcher clones
state dictionaries
temporary loader tuples
diagnostic buffers
trace buffers
```

Clear only proven duplicate owners:

```text
construction state dictionaries
completed futures retaining redundant tuples
temporary patched clones
stale diagnostic buffers
temporary file-read objects
```

Retain:

```text
one canonical CLIP
one canonical UNET
one underlying diffusion model
one canonical VAE if Phase C wins
exact bridge/seed references required by request execution
```

## Advanced contingency: storage/copy-plan optimization

Only when Phase 1 proves that per-tensor layout/traversal is the bottleneck:

- snapshot an ordered tensor copy plan;
- group by source storage, destination device, and dtype;
- reduce repeated Python introspection;
- investigate safe batched copies;
- investigate storage coalescing only on an isolated branch.

Do not rewrite tensor storage layout without proof. It can break parameter aliasing, patches, state-dict semantics, and snapshot identity.

## Memory request

Reduce requested CPU memory only after measured restored RSS and peak usage fall with margin.

Do not reduce memory merely to influence scheduling.

## Acceptance

```text
no model file reload
same exact model identities
restore median does not regress
restore worst-case improves or snapshot RSS falls materially
no OOM or page-fault increase
```

## Expected result

```text
0–0.3s median
0.2–0.8s tail improvement
```

---

# PHASE 7 — Persistent exact-conditioning cache, last

## Scope

This is for repeated Playground experiments where prompt and CLIP identity remain unchanged while seed, steps, CFG, denoise, or other axes change.

It is not part of the universal unique-prompt sub-13 claim.

## Exact key

```text
workspace/user isolation boundary
exact positive/negative text hashes
role
tokenizer identity
CLIP object/model identity
CLIP type
encode options
workflow hash
prompt-bundle identity
custom-node generation
deployment combined hash
conditioning schema version
```

## Stored value

```text
conditioning tensor(s) on CPU
pooled output when present
shape/dtype metadata
semantic metadata
creation time
key version
```

Never put plaintext prompts in filenames or logs.

## Required behavior

```text
bounded LRU/TTL
atomic write
exact validation
single-flight population
one elected fallback
late background completion cannot overwrite fallback
cache corruption falls back normally
cross-user access impossible
```

## Acceptance

```text
hit avoids real CLIP encode
miss remains equivalent to current production
no stale or cross-identity reuse
no universal cold benchmark uses a cache hit
```

## Expected result

```text
2.5–3.5s on a repeated-prompt hit
0s on a unique-prompt miss
```

---

## 6. Separate product-level track — Batch one requested experiment per remote invocation

This is the largest product-throughput opportunity but is not part of the single-image true-cold sub-13 benchmark.

For a requested experiment containing multiple images:

```text
one remote invocation
first image pays cold preparation
subsequent images reuse the already active container state
container exits normally after the requested batch
```

This does not require:

```text
min_containers > 0
keep-warm traffic
longer scaledown
scheduled warmups
```

The post-full-pass warm evidence suggests subsequent images can approach approximately `6–7s` of application work.

Requirements:

```text
per-image progress
per-image metadata
independent seed and axis values
bounded queue
cancellation
failure isolation
partial-result preservation
no state leak between users/workspaces
```

This track may be designed in parallel with the single-cold roadmap, but its gains must be reported separately.

---

## 7. What can be snapshotted, parallelized, and cached

### 7.1 Snapshot

High-value safe candidates:

```text
canonical CLIP and exact loader output        already present
canonical UNET and exact loader output        already present
Step 3 structural execution seed              being validated
canonical VAE and loader output               Parallel Track C
certificate and production registry           Parallel Track A
tokenizer/configuration                        verify and retain
storage registries/copy-plan metadata          Phase 1/6
sampler static identity and settings           Parallel Track A
compiled Python graph topology                 Step 3/static package
pre-imported custom-node modules               Phase 3/static package
```

Do not snapshot:

```text
generated images
latents
random/seed state
request IDs
progress/cancellation state
arbitrary prompt conditioning
mutable PromptExecutor outputs
GPU objects or CUDA handles
completed request-owned futures
```

### 7.2 Parallelize

Safe or conditionally safe:

```text
Step 3/certificate validation with model page readiness
prompt tokenization with UNET page readiness
CLIP encode with controlled UNET H2D, only after evidence
VAE file/readiness during sampling
local handle resolution with local plan materialization
output metadata preparation with image encoding
read-only CLIP and UNET residency inspection
```

Keep serialized:

```text
ComfyUI loaded-model cache mutation
model offload/eviction
ModelPatcher mutation
CacheDiT attachment
Sage/global patch mutation
sampler start relative to active model mutation
VAE GPU commit relative to sampler unless measured safe
```

### 7.3 Cache

Universal/safe:

```text
local Modal client/class/instance handle
active profile
certificate/registry package
Step 3 structural seed
loader output identities
tokenizer/token IDs where exact
compiled Triton/Torch-extension artifacts in the image
static tensor/copy-plan metadata
```

Hit-only and last:

```text
persistent exact conditioning tensors
```

Not useful/safe as a cache:

```text
GPU residency across true-cold containers
OS page-cache warmth
random state
generated outputs for arbitrary requests
```

---

## 8. Parallel development policy

### Read-only work that may run in parallel

```text
UNET core-path trace
CLIP core-path trace
sampler first-use trace
local handle design
certificate package design
VAE snapshot design
output transport audit
```

### Implementation work that must not have concurrent writers

Do not allow simultaneous writers to:

```text
comfymodal_runtime/model_preload.py
comfymodal_runtime/runtime_executor.py
comfymodal_runtime/modal_app.py
comfymodal_runtime/runtime_bootstrap.py
```

UNET and CLIP implementation both touch the coordinator and must merge sequentially even if their research occurs in parallel.

Independent implementation branches may safely target:

```text
modal_transport.py / modal_client.py            local handle
certificate/static package helpers              certificate
output transport helpers                        output path
```

Every commit must be attributable to one workstream.

---

## 9. Paid-run discipline

No implementation prompt may automatically authorize a large matrix.

### Default per phase

```text
local tests and static review: no paid run
instrumentation/deployment validation: 1 paid establishment request
candidate A/B: 1 paid true-cold request per candidate
winner validation: 3 paid true-cold requests
default maximum: 5 paid requests per phase
```

Any additional paid request requires explicit user approval.

### Immediate stop conditions

Stop after the first request when:

```text
wrong app/class/image
wrong diagnostic mode
reused container when true-cold required
wrong thread topology
missing required marker
duplicate CLIP encode
duplicate UNET transfer
wrong sampler settings
output mismatch
waterfall cannot reconcile
```

Do not continue a matrix with invalid instrumentation.

### Final counted requests

Each must prove:

```text
fresh restored_instance_id
restore_count=1
request_count=1
production profile
memory snapshot restore
same workflow/model/sampler settings
```

Report every attempt, including failures and platform outliers.

---

## 10. Validation metrics for every performance commit

### Identity and correctness

```text
workflow hash
source workflow hash
deployment hash
custom-node generation
CLIP object identity
UNET patcher identity
underlying diffusion identity
VAE identity when relevant
one CLIP encode
one UNET transfer
one CacheDiT attachment
eight sampler steps
output equivalence
```

### Non-overlapping timing

```text
local setup
local handle/submission
platform/host restore
application restore
restore-to-method
method setup
Step 3/executor
first node to CLIP
CLIP readiness
CLIP encode
UNET readiness
UNET H2D
sampler startup
sampling
post-sampling
VAE
output
return
```

### Resource and hidden-work checks

```text
process CPU and effective cores
minor/major faults when relevant
read overlap
GPU allocated/reserved
GPU utilization
memory-controller utilization
PCIe when exposed
active futures
mutation-lane owner
active reads/writes
watchdog state
```

### Reconciliation

```text
absolute error <= max(50ms, 0.5% of command-to-response)
known platform time must not remain in generic residual
```

---

## 11. Cumulative performance projection

Starting median:

```text
approximately 19.24s
```

Measured, non-overlapping target path:

| Completed work | Projected median |
|---|---:|
| Step 3 validated baseline | `18.9–19.3s` |
| UNET stable and mostly hidden | `16.8–17.8s` |
| CLIP readiness reduced | `14.2–16.0s` |
| Sampler restored to 3.7–4.0s | `13.1–14.9s` |
| Combined bounded overlap | `12.2–14.2s` |
| Certificate, local handle, VAE, output | `11.5–13.3s` |
| Ownership/tail cleanup | `11.3–13.1s` |

These ranges are not additive promises. UNET and CLIP overlap interact, and a gain moved beneath another stage must be counted only once.

### Honest target assessment

```text
median below 15s: high probability if Phases 1–3 succeed
median below 13s: plausible and supported by measured warm/historical floors
3/3 below 13s: requires UNET tail elimination plus near-target CLIP and sampler
worst-case below 13s with platform >6s: stretch unless app path approaches warm floor
```

The friend’s reported sub-13 result is consistent with the observed physical floor, but this plan relies only on measurements available in this repository and its logs.

---

## 12. Old-to-new roadmap mapping

| Old step | New location |
|---|---|
| Step 3 — Cold cache parity | Phase 0; finish and freeze |
| Step 4 — Local Modal handle | Parallel Safe Track B |
| Step 5 — Preserve 3.7–4.0s sampler | Phase 3, elevated |
| Step 6 — Exact prompt conditioning | Phase 2, rewritten around model readiness because prefill already works |
| Step 7 — Early UNET activation | Phase 1, now attribution-gated because contention and 7.61s tail are proven risks |
| Step 8 — Sequential CLIP/UNET order | Folded into Phase 4 |
| Step 9 — Bounded concurrency | Folded into Phase 4 with stricter one-run candidate gates |
| Step 10 — Snapshot ownership trim | Phase 6 |
| Missing from old plan | VAE snapshot, certificate package, output path, batching, exact conditioning cache last |

---

## 13. Final definition of done

The roadmap is complete only when one production deployment produces:

```text
3/3 verified true-cold command-to-response <13.0s
median <=12.5s
worst <=12.9s
```

and all three runs show:

```text
min_containers=0
scaledown_window=4
no warmup request
no GPU snapshot
one CLIP encode
one UNET transfer
one CacheDiT attachment
sampling <=4.10s
graph-visible CLIP <=1.00s
graph-visible UNET wait <=0.50s
complete output equivalence
no hidden request-owned work
waterfall reconciliation within tolerance
```

A repeated-prompt conditioning-cache hit or a reused remote container cannot be counted toward this acceptance.

---

## 14. Recommended immediate next action after Step 3

After the Step 3 validation commit is available:

1. Freeze three low-overhead true-cold baseline runs.
2. Correct any remaining waterfall platform/residual error.
3. Perform one genuine UNET-focused deep request.
4. Write the Phase 1 implementation prompt from the measured branch:
   - restored-page readiness;
   - tensor traversal;
   - H2D/copy;
   - or synchronization/cache publication.
5. Do not run a full schedule matrix until the underlying `2.02–7.61s` variance is understood and corrected.

This is the highest-value, lowest-regret next move toward consistent sub-13 production performance.
