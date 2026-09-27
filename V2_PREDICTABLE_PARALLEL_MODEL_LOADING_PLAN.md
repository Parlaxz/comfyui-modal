# V2 Predictable Parallel Model Loading Plan

## Objective

Maximize useful overlap among UNET, CLIP, VAE, certificate lookup, and exact CLIP conditioning while preserving:

- V2's short TTExec;
- deterministic execution order;
- one physical load per exact model identity;
- no duplicate fallback loads;
- no simultaneous mutation of ComfyUI's global GPU/model cache;
- no model-loading work racing the sampler;
- a substantially smaller implementation than V1.

The target remains approximately `14–15s` remote execution and `20–21s` representative total wall time on RTX PRO 6000.

## Evidence from the verified deployment

Verified deployment identity:

- Workspace: `ws_228aedb01781`
- Environment: `main`
- App: `stable-modal-comfy-v2-diagnosis`
- Class: `ModalRuntimeEntrypointV2`
- Image: `im-2yVx6w2IIItdRJaNW2LosL`
- GPU: RTX PRO 6000

Relevant artifacts:

- `C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\comfymodal-data\benchmarks\runs\2026-07-19_12-09-54`
- `C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\comfymodal-data\benchmarks\runs\2026-07-19_12-13-15`

Representative certificate-hit runs:

- Remote execution: `26.38–26.73s`
- Submit to entry / TTExec: `4.82–5.48s`
- Pre-sampler: `19.45–19.87s`
- CLIP encode: `6.56–6.98s`
- Sampler: `3.728–3.732s`
- UNET graph wait: approximately `0.01ms`
- CLIP graph wait: approximately `0.01ms`

Observed loading timeline from the July 19 logs:

```text
12:17:07.480  restore returns
12:17:07.485  CLIP physical read starts (7.67GB)
12:17:07.498  UNET physical read starts (11.74GB)
12:17:10.618  CLIP physical read completes (~3.13s)
12:17:10.804  UNET physical read completes (~3.31s)
12:17:14.810  blocking Modal Volume warning during certificate lookup
12:17:15.153  certificate hit
12:17:15.475  VAE physical read starts (319.8MB)
12:17:15.597  VAE physical read completes (~122ms)
```

Established conclusions:

1. UNET and CLIP physical reads already overlap successfully.
2. VAE starts approximately eight seconds later and can safely be prepared earlier.
3. Graph model waits are effectively zero, so physical loading alone is not currently exposed at graph demand.
4. Exact CLIP prefill skipped because its one static encode had no positive/negative role.
5. Certificate lookup uses a blocking Modal interface in an async path and overlaps part of model preparation, but remains on the critical path after the model reads finish.
6. Background ComfyUI-Manager and executor threads survive past result delivery and can delay container shutdown by up to 30 seconds.

## Design principle

Use a dependency graph with maximum parallel work on independent resources and deterministic serialization only where shared global/GPU state is mutated.

Do not use unrestricted loader threads.

## Proposed execution graph

```text
graph_execution_start
│
├── Certificate lookup future
│   ├── async volume synchronization, if required
│   ├── certificate file read
│   └── identity/component validation
│
├── UNET preparation future
│   ├── physical read / state-dict decode
│   ├── CPU object preparation
│   └── GPU/cache commit through mutation lane
│
├── CLIP preparation future
│   ├── physical read / state-dict decode
│   ├── CPU object preparation
│   └── GPU/cache commit through mutation lane
│
└── VAE preparation future
    ├── physical read / state-dict decode
    ├── CPU object preparation
    └── GPU/cache commit through mutation lane

After required model preparation:

UNET ready + CLIP ready + GPU mutation lane available
└── exact CLIP conditioning future

After conditioning is ready:

UNET ready + exact conditioning ready + VAE safely prepared
└── PromptExecutor / sampler
```

## Concurrency policy

### Parallel work

These operations may run concurrently when they operate on different exact model identities:

- model-file reads;
- safetensors parsing into independent CPU state;
- CPU-side model construction proven not to mutate shared ComfyUI state;
- certificate I/O;
- workflow validation and graph preparation;
- output-independent metadata work.

### Serialized work

One coordinator-owned GPU mutation lane must serialize:

- insertion/removal in ComfyUI's global loaded-model cache;
- GPU model materialization and placement;
- model offload/eviction;
- global model patches;
- CLIP encode while another loader is mutating GPU/cache state;
- VAE GPU preparation;
- sampler startup and execution relative to all model mutations.

Initial deterministic priority:

```text
UNET GPU/cache commit
→ CLIP GPU/cache commit
→ exact CLIP encode
→ VAE GPU/cache commit
→ sampler
```

The priority may change only after measurements prove another ordering is faster and equally stable.

## Single-flight state machine

Each exact model key owns one future and one state machine:

```text
PENDING
→ READING
→ CPU_READY
→ GPU_COMMITTING
→ READY
```

Failure:

```text
any state → FAILED
```

Exact key inputs must include:

- model path(s);
- model/custom-node generation;
- loader class;
- model type;
- dtype;
- device/load options;
- patches/adapters that affect the resulting object.

Rules:

1. A second consumer attaches to the existing future.
2. No fallback loader starts while the future is pending.
3. A failure becomes terminal before fallback is permitted.
4. Only one consumer is elected to execute fallback.
5. A late background completion cannot overwrite a fallback result.
6. Request cancellation cannot leave a loader mutating global GPU state.

## Exact CLIP conditioning

CLIP conditioning is a dependent fourth lane, not an independent speculative task.

Safe start condition:

```text
matching CLIP future is READY
AND conflicting model GPU/cache mutation is complete
AND exact prompt bundle is eligible
AND the conditioning single-flight key is not already pending/ready
```

For the current workflow, first test `lane=all` because there is exactly one statically resolved encode and `critical` currently rejects it for missing role metadata.

Required experiment assertions:

- one `execution_prefill_scheduled`;
- one `execution_prefill_completed`;
- no CLIPTextEncode during restore;
- no duplicate graph encode;
- no overlap with UNET/CLIP/VAE GPU/cache commits;
- graph-visible conditioning wait at or below `200ms`;
- exact conditioning and final output equivalence.

After proof, replace `lane=all` with graph-topology role inference:

- infer positive/negative only from explicit sampler conditioning edges;
- ambiguous entries remain ineligible;
- fallback remains the original CLIPTextEncode implementation.

## Certificate lookup overlap

Instrument these operations separately:

- `volume.reload()` or `await volume.reload.aio()`;
- `volume.exists()`;
- `volume.read_bytes()`;
- JSON decode;
- schema and identity checks;
- component validation.

The lookup should begin at `graph_execution_start` alongside all three model preparations.

Do not move it into restore or snapshot startup.

If mounted certificate files are coherent without per-request reload, test direct read as a controlled candidate. All missing, malformed, stale, or mismatched states must still fail closed to full preflight and validation.

## Implementation phases

### Phase 0 — Establish substage evidence

Add timing/events for each model lane:

- submitted;
- physical read start/end;
- CPU preparation start/end;
- GPU mutation wait start/end;
- GPU commit start/end;
- ready/failed;
- graph demand and graph wait.

Do not infer these boundaries from a monolithic loader duration. Inspect ComfyUI core in the parent repository and identify the actual read, construction, and GPU/cache mutation points.

Gate: one verified deployment must expose a complete timeline without changing execution behavior.

### Phase 1 — Add VAE to early preparation

Extend the existing V2 coordinator rather than creating another subsystem:

- add a VAE future and exact identity;
- submit it with UNET and CLIP at graph execution start;
- wrap VAELoader graph consumption using the existing bridge pattern;
- preserve original-loader fallback;
- verify exactly one VAE read and one prepared consumption.

Gate: VAE graph wait remains near zero, no output changes, no TTExec regression.

### Phase 2 — Introduce the GPU mutation lane

Identify which parts of the original ComfyUI loaders mutate global/GPU state. Protect only those sections with one coordinator-owned semaphore/lock.

Do not serialize physical reads or proven-independent CPU preparation.

Gate: repeated stress tests show no duplicate cache entries, offload races, OOM, deadlock, or output mismatch under one- and two-worker configurations.

### Phase 3 — Activate exact execution prefill

- test `lane=all` on the current single-encode workflow;
- schedule after graph start;
- consume the same future from graph CLIPTextEncode;
- then implement minimal role inference after the gain is established.

Gate: graph CLIP encode/wait at or below `200ms`, no restore/TTExec shift, identical conditioning/output.

### Phase 4 — Make certificate lookup asynchronous or direct

- instrument first;
- use Modal's `.aio()` API if synchronization is required;
- otherwise test coherent direct mounted-file read;
- preserve fail-closed semantics.

Gate: certificate-hit graph-start-to-executor interval materially decreases without stale certificate use.

### Phase 5 — Shutdown discipline

The runtime must not return while request-owned preparation futures remain active.

- ensure all request futures are terminal;
- close/recycle the V2 coordinator pool safely;
- ensure subsequent requests can recreate it;
- disable ComfyUI-Manager network registry refresh before it starts in production;
- verify no `comfymodal-restore_*` or registry fetch threads delay container shutdown.

Gate: no Modal warning about live background threads after container exit.

## Test requirements

### Unit/state-machine tests

- one future per exact key under concurrent consumers;
- changed identity creates a new future;
- duplicate fallback cannot occur;
- late success after failure cannot publish;
- cancellation reaches a terminal state;
- one- and two-worker configurations complete without deadlock;
- VAE uses the same bridge/fallback contract as UNET and CLIP;
- GPU mutation lane never has more than one owner;
- sampler cannot begin while the mutation lane is active;
- CLIP encode cannot overlap a conflicting GPU commit;
- diagnostics distinguish preparation waits from true graph waits.

### Integration tests

- delayed UNET, fast CLIP, fast VAE;
- fast UNET, delayed CLIP, fast VAE;
- simultaneous model completion;
- loader exception in each lane;
- certificate hit/miss/error while loaders run;
- prefill hit/miss/error;
- missing-node repair invalidating cached validation;
- repeated request after coordinator shutdown/recreation.

## Benchmark protocol

For every candidate:

1. Deploy explicitly to workspace `ws_228aedb01781`, environment `main`.
2. Verify app, class, image ID, GPU, workflow hash, and expected trace markers before counting a paid run.
3. Perform one establishment request.
4. Perform four verified cold certificate-hit runs with 60-second gaps.
5. Save all timestamped artifacts.
6. Report every run, including Modal scheduling outliers.

Primary metrics:

- total wall;
- submit to entry / TTExec;
- remote execution;
- graph start to executor start;
- each model read/CPU/GPU-commit duration;
- model graph waits;
- conditioning wait/encode;
- sampler;
- VAE decode;
- output-to-return;
- background-thread shutdown delay.

Acceptance:

- no app-controlled TTExec regression;
- remote execution median at or below `15s`;
- representative total wall median at or below `20–21s` while reporting scheduling separately;
- graph model waits near zero;
- conditioning wait at or below `200ms`;
- no duplicate loads/encodes;
- no loader/cache races, deadlocks, OOM, timeouts, fallback errors, or output differences;
- no live request-owned background threads at container exit.

## Scope discipline

- Extend `ModelPreloadCoordinator` and `V2LoaderBridge`; do not create a second loading framework.
- Prefer small explicit state and locks over V1's broad patch network.
- Do not add persistent model or conditioning caches until the execution-phase pipeline is proven.
- Do not change sampler algorithms, model precision, workflow semantics, or output quality in this effort.
- Do not claim a phase win unless total wall and remote execution improve without TTExec regression.
