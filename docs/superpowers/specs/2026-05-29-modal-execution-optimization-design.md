# Modal Execution Optimization Design

## Goal

Reduce effective cold-start and execution overhead for Modal-hosted ComfyUI without changing prompt semantics, while keeping code changes precise, local, and easy to roll back.

## Design principles

- Correctness before speed.
- The exact API-format prompt produced by local ComfyUI must be the exact prompt executed remotely.
- Prefer precise edits over sweeping rewrites.
- Keep the current subprocess ComfyUI server as the stable default.
- Treat in-process execution as experimental only.
- Keep `scaledown_window=4` and `min_containers=0` unchanged.
- Do not turn snapshots into per-request or per-workflow artifacts.

## Current issues

- Startup still does avoidable work on the critical path.
- Restore/startup behavior is not instrumented precisely enough to explain current ~40s cold starts.
- The execution path has no first-class prompt-integrity guardrails despite a prior regression where workflow inputs stopped affecting output.
- The current architecture has no real cancellation path.
- The code currently allows more execution-layer concurrency than is desirable for one ComfyUI server on one GPU.
- Snapshot invalidation rules are implicit even though Modal does not refresh snapshots when Volume contents change.

## Hard constraints

- No prompt mutation.
- No injected nodes into user workflows.
- No checkpoint rewriting.
- No auto-following per-request model selection into snapshot state.
- No broad architecture replacement as part of the first optimization pass.

## Approved scope

### Keep

- Subprocess ComfyUI runtime as default.
- GPU snapshots.
- Sync `/comfymodal/prompt` compatibility path.
- Existing Modal deployment shape.

### Add

- Prompt integrity layer.
- Precise startup/restore cleanup.
- Explicit snapshot/runtime versioning.
- Read-only model-stack tracking.
- Optional async submit/status/cancel API.
- Experimental in-process backend behind a flag.

### Cut from initial implementation

- Auto-snapshotting or preloading the last arbitrary workflow-selected model stack.
- Any warmup that depends on mutating or reconstructing the user prompt.
- Any change that makes in-process execution the default path.

## Design

### 1. Runtime strategy layer

The runtime layer provides two execution backends:

- `subprocess` — default and stable.
- `in_process` — experimental, opt-in only.

Required behavior:

- Backend selection is controlled by config or environment.
- `subprocess` remains the fallback for all unsupported or unhealthy cases.
- If `in_process` fails once inside a container, the container sticks to `subprocess` for the rest of its lifetime.
- Backend choice must not alter prompt payload shape or execution semantics.

### 2. Prompt integrity layer

This is a first-class correctness guard.

The system should capture enough data to prove that remote execution matches local intent:

- hash the raw local `/prompt` payload as received by `__init__.py`
- hash the final payload submitted from Modal to ComfyUI
- log stable execution fields when present:
  - cfg
  - steps
  - seed
  - sampler
  - scheduler
  - denoise
  - width
  - height
  - prompt text hash

Acceptance rule:

- Warmup, retry, async delivery, and backend selection must never mutate the user prompt unexpectedly.

This layer exists specifically to prevent recurrence of the earlier “inputs ignored” regression.

### 3. Model-stack tracker

Add a read-only tracker that extracts the last successful model stack from workflow JSON.

Track where possible:

- checkpoint / diffusion model / UNet / GGUF
- text encoder
- VAE
- LoRA
- ControlNet
- IPAdapter
- workflow family
- relevant loader node classes
- filenames and light metadata when available

The tracker is for observability and optional future warmup profiles only.

It must:

- never rewrite workflows
- never choose a snapshot dynamically per request
- never invalidate snapshots on every workflow change

### 4. Warmup executor

Warmup is best-effort and separate from user prompts.

Initial implementation rules:

- disabled by default
- must be independently configurable
- logs warmup duration separately from startup duration
- uses a tiny internal warmup action only
- must not reuse the user’s prompt

Initial safe warmup target:

- ComfyUI internal registration or object-info style warmup
- optional named warmup profile later, not arbitrary last-used workflow replay

Important non-goal:

- do not automatically preload the last successful arbitrary model stack into snapshot state in the first implementation

### 5. Snapshot versioning

Snapshot invalidation must be explicit.

Maintain a runtime snapshot key derived from:

- app/runtime version
- ComfyUI version or commit
- comfyui-modal worker version
- custom-node manifest hash
- warmup feature version
- selected warmup profile name and version
- GPU type

Separate this from warmup target metadata.

Rules:

- runtime configuration changes may require redeploy or snapshot refresh
- user workflow changes update warmup metadata only
- material model/custom-node volume changes may mark the current warmup profile stale
- snapshot invalidation must not happen on every user request

### 6. Execution concurrency split

Keep execution conservative.

For the GPU execution worker:

- single prompt at a time
- `max_inputs=1`
- `target_inputs=1`

Reason:

- one ComfyUI server process on one GPU should not accept multi-prompt mutation/concurrency without deliberate proof that it is safe.

For lightweight API/status/cancel paths:

- async I/O concurrency is allowed

This separates user-facing responsiveness from risky multi-prompt execution concurrency.

### 7. Async job layer

Add an optional async job API with:

- submit
- status
- cancel
- result

The current sync `/comfymodal/prompt` route remains as a compatibility wrapper:

1. submit
2. wait
3. return final result in the current format

Cancel behavior:

1. mark job as cancelling
2. call ComfyUI interrupt or queue-cancel if available
3. if the subprocess is wedged, escalate to restarting ComfyUI
4. avoid killing the whole Modal container unless the worker is unhealthy

### 8. Startup and restore optimizer

This is the highest-value first pass.

Approved precise changes:

- add structured timing around each startup step
- replace unnecessary heavy symlink teardown with lighter path handling
- remove or defer redundant `vol.reload()` calls from cold-start critical path
- defer runtime-state scans unless explicitly needed
- tighten `resync_runtime` locking and lifecycle behavior
- use prompt-safe, minimal restore checks
- reuse a local HTTP client/session instead of repeated one-off localhost requests
- URL-encode view/download query parameters correctly

This phase must not change core execution semantics.

### 9. Output layer

Keep the current direct-return path for small outputs.

Add optional large-output handling later:

- small images may continue inline
- large videos may use a dedicated output path such as Volume-backed retrieval
- fetch multiple outputs in parallel where safe
- avoid unnecessary copies

## Expected performance impact on A100

Current reported baseline:

- cold start: ~40s
- execution time: ~30s

User-provided context and prior testing indicate that **subsequent boots should plausibly reach ~3-5s** when snapshot restore is working properly.

That means the performance model must distinguish:

1. **first boot after deploy / snapshot creation**
2. **subsequent boots after scale-to-zero / snapshot restore**

### Interpreting the current ~40s baseline

If the observed ~40s applies to subsequent boots as well, then one of these is likely true:

- snapshots are not actually being created or used
- GPU snapshot restore is not functioning as intended
- restore is still paying startup-class work somewhere in the path
- the measured number includes first deploy boot rather than true restore behavior

In other words, a ~40s restore path should be treated first as a **snapshot-path correctness problem**, not just a tuning problem.

### Performance targets

| Metric | First boot | Subsequent boot | Notes |
|---|---|---|---|
| Boot to ComfyUI ready | ~25-40s acceptable | **~3-5s target** | Subsequent target assumes working snapshot restore |
| First prompt execution | ~28-35s | ~28-35s | Dominated by inference and first model load |
| Warm steady-state prompt | ~25-32s | ~25-32s | Assumes model/runtime already hot |

### Conditions required for ~3-5s subsequent boots

1. GPU snapshots must actually be active and restoring useful state.
2. `restore()` must be effectively O(1).
3. No heavy volume reload, sync, install, or scan work may occur on restore.
4. Modal must be able to provision or reuse compatible A100 capacity quickly enough.

This spec only controls conditions 2 and 3 directly, and can instrument 1 clearly.

### Phase 1 — correctness + startup cleanup

Primary goals:

- prove whether the app is taking the `startup(snap=True)` path or the `restore(snap=False)` path
- make restore unequivocally cheap
- remove avoidable work from startup and restore

Expected effect:

- **first boot:** likely improve from ~40s to roughly **~32-36s**
- **subsequent boots:** should move toward the **~3-5s** target if snapshot restore is functioning properly
- **execution time:** **~0-1s** direct improvement

Confidence:

- high for first-boot savings
- medium for the 3-5s subsequent-boot target because part of that depends on Modal snapshot behavior and A100 provisioning conditions outside the repo

Most likely sources of savings:

- proving and instrumenting snapshot lifecycle behavior
- making `restore()` unconditionally cheap
- removing avoidable reload work from startup
- overlapping startup work better
- cutting repeated localhost connection/setup overhead

### Phase 2 — async jobs + cancellation

Expected effect:

- direct generation speed improvement: **~0s** in normal successful runs
- large UX improvement for retries, queueing, and aborting mistakes
- cancellation can save nearly a full run in failure or user-abort cases

Confidence: medium.

This phase mostly improves delivery semantics and wasted-work avoidance, not raw inference speed.

### Phase 3 — conservative warmup

Expected effect:

- first boot may become slightly slower if warmup is enabled
- first prompt after restore may become **~3-8s faster**
- net value depends on how many prompts a container serves before scale-to-zero

Confidence: medium.

Because `scaledown_window=4` stays fixed, warmup may have limited payoff unless users commonly submit several prompts within one container lifetime.

### Phase 5 — experimental in-process backend

Expected effect if it works well:

- first-boot cold start could improve by **~8-12s** beyond the stable subprocess path
- steady-state execution likely improves only **~0.5-2s**

Confidence: low.

Risk is high enough that this is not justified as an early default path.

### Summary

Best expected low-risk win:

- **first boot should realistically drop from ~40s to roughly ~32-36s on A100**
- **subsequent boots should target ~3-5s, provided snapshot restore is actually working and restore remains O(1)**

Best early raw execution win without sweeping changes:

- modest, likely **sub-second to low-single-digit seconds**, unless conservative warmup later proves well amortized.

### Required instrumentation for validation

Before trusting performance claims, add structured logs that make these cases explicit:

- `lifecycle=startup snap=True`
- `lifecycle=restore snap=False`
- restore duration
- startup step durations
- first prompt timing after restore

Without this, it is impossible to distinguish a true snapshot restore from a full boot that merely happened after scale-to-zero.

## Risks

- Prompt-integrity checks may be too shallow if they only log hashes and not selected semantic fields.
- Snapshot invalidation may be wrong if runtime and warmup metadata are mixed together.
- Async cancel may accidentally kill too much if it escalates to process restart too aggressively.
- Multi-prompt concurrency may reappear accidentally unless execution limits are explicit.
- Experimental in-process execution may create subtle compatibility failures with custom nodes or ComfyUI internals.

## Testing

Add or update tests for:

1. prompt payload identity between local receipt and remote submission
2. startup/restore timing instrumentation presence and structure
3. restore path skips unnecessary heavy work
4. single-execution worker guardrails
5. model-stack tracker extracts metadata read-only
6. snapshot-version metadata is computed deterministically
7. cancel path interrupts the active remote job without mutating prompt payloads
8. sync `/prompt` wrapper still returns the current response shape
9. experimental backend fallback returns to subprocess cleanly after failure

## Phase plan

### Phase 1 — Safe correctness + startup cleanup

- prompt integrity logging and checks
- precise startup/restore cleanup
- HTTP/session reuse
- volume reload/commit lifecycle tightening
- metadata caching where safe
- subprocess default preserved

### Phase 2 — Async job API + cancellation

- submit/status/cancel/result
- sync compatibility wrapper retained

### Phase 3 — Conservative warmup

- model-stack tracking retained as read-only metadata
- tiny internal warmup only
- disabled by default

### Phase 4 — Snapshot versioning

- explicit runtime versioning
- explicit snapshot schema/profile versioning

### Phase 5 — Experimental in-process executor

- backend flag only
- sticky fallback to subprocess

## Non-goals

- changing `scaledown_window=4`
- changing `min_containers=0`
- per-request snapshot selection
- auto-following arbitrary last-used model stacks into snapshot state
- sweeping replacement of the subprocess backend during the first optimization pass
