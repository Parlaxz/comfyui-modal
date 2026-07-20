# V2 Wall-Time Optimization Plan

## Goal

Keep V2 time-to-execution at approximately 3–4 seconds while reducing Modal execution time from approximately 26 seconds to 14–15 seconds and total user-visible wall time to approximately 20 seconds. V1 is a performance reference, not an implementation template.

## Established evidence

- V1 median wall time: 21.231 seconds.
- V2 baseline median wall time: 39.152 seconds; optimized median: 34.617 seconds.
- V1 runtime CLIP encode is approximately 0.4 ms because exact prompt conditioning is prepared before graph demand. V2 runtime CLIP encode is approximately 2.13 seconds.
- V2 UNET graph wait is already approximately 0.32 ms and is not the cause of the regression.
- VAE decode differs by approximately 10 ms and is not material.
- V2 sampler is approximately 300 ms slower, but the compared workflow hashes differ, so the cause is not established.
- V2 preflight reports 8.8–12.6 seconds, but incomplete phase boundaries currently prevent determining its non-overlapping critical-path cost.
- V2 currently performs preflight before checking its validation certificate in `comfymodal_runtime/modal_app.py`, so a certificate hit does not avoid preflight.

## Constraints

1. Do not move work into Modal time-to-execution.
2. Do not reproduce V1's broad speculative UNET/CLIP/VAE concurrency.
3. Prefer existing V2 coordinator, bridge, trace, and certificate structures.
4. Every optimization must improve total wall time, not merely move time between phases.
5. Preserve fallback behavior on missing, stale, or invalid optimization state.

## Phase 1: Complete critical-path instrumentation

- Emit an authoritative remote container/method-entry boundary for V2 execution.
- Preserve local submit, remote entry, graph start, PromptExecutor start/end, sampler, VAE, and output completion timestamps in one merged trace.
- Make pre-sampler and post-sampler derivation possible without summing overlapping duration fields.
- Ensure legacy timing serialization contains the V2 stage timestamps used by the benchmark collector.
- Add focused tests for trace merging and phase boundary presence.

Gate: three cold runs must expose non-null submit-to-entry, pre-sampler, sampler, and post-sampler fields that reconcile with wall time.

## Phase 2: Certificate-gated preflight fast path

- Resolve the exact V2 certificate identity before expensive preflight work.
- Extend the certificate payload to record successful deterministic preflight completion under that identity.
- On an exact certificate hit, skip only the certified deterministic preflight work.
- Keep request-specific checks, production authorization, and PromptExecutor validation behavior intact.
- On any miss, malformed certificate, identity mismatch, or version mismatch, run the existing preflight path unchanged.
- Do not execute preflight during restore or snapshot startup.

Expected opportunity: the largest part of the remaining 8–10 second execution gap, subject to Phase 1 evidence.

## Phase 3: Execution-phase exact CLIP single-flight

- Reuse V2's existing prefill result cache and loader bridge rather than adding a new cache subsystem.
- Schedule exact critical-role CLIP conditioning only after V2 graph execution has started.
- Make the prefill job depend on completion of the existing UNET and CLIP preparation futures before GPU encoding begins.
- Permit only one prefill computation for a given prepared CLIP object and text.
- Make graph `CLIPTextEncode` consume or wait for that same future; never launch a duplicate encode.
- Preserve the original node implementation as the fallback for ineligible prompts, failures, or identity mismatches.

Expected opportunity: hide part or all of the approximately 2.13-second graph-time CLIP encode behind remaining execution setup without extending TTExec.

## Deferred unless measurements justify them

- CLIP safetensors `read_bytes` path.
- Physical model-read deduplication.
- `load_models_gpu` fast paths.
- Torch compilation.
- Persistent conditioning caches.
- VAE warmup.
- Additional speculative model-loading workers.

## Verification protocol

For every deployed phase:

1. Use the same RTX PRO 6000 class, workflow hash, seed, options, and deployment configuration.
2. Perform one establishment/profile run.
3. Perform three measured cold runs separated by 20 seconds.
4. Save every run as timestamped JSON.
5. Report total wall, Modal TTExec, Modal execution, `t3b_to_t8`, restore, preflight, CLIP encode/wait, sampler, VAE, and output collection.

Acceptance gates:

- No app-controlled increase in TTExec; UI TTExec median non-inferiority margin is 250 ms.
- Median execution time at or below 15 seconds.
- Median total wall time at or below 20–21 seconds.
- Three of three runs complete without fallback races, duplicate model loads, timeouts, or output regressions.
- Revert any phase that increases total wall time by more than 2%, increases TTExec by more than 500 ms, or introduces an execution failure.

Paid Modal generations are not run automatically. Deployment benchmarking requires an explicit manual run or separate authorization.

## Implementation status

Implemented locally on 2026-07-19:

- V2 request-entry and legacy-stage trace continuity.
- Schema-v2, fail-closed validation/preflight certificates.
- Certificate lookup before deterministic preflight.
- Missing-node-repair invalidation of cached validation output.
- Restore-time UNET/CLIP preparation with CLIPTextEncode deferred until execution.
- Execution-phase, critical-role CLIP single-flight after `graph_execution_start`.
- Both-model completion barrier before CLIP encoding.
- Execution-prefill diagnostics isolated from graph-demand wait metrics.
- Focused regression coverage for trace merging, certificate safety, fallback behavior, lane modes, and one/two-worker synchronization.

Local verification:

- `168` focused tests passed.
- Python compilation passed for changed runtime modules.
- `git diff --check` passed.
- Both Oracle review gates approved after remediation.

## 2026-07-19 verified deployment benchmark

The first attempted benchmark was invalid because the CLI deployed into a different Modal workspace than the local bridge used. Those results are discarded.

The corrected deployment target was:

- Workspace: `ws_228aedb01781`
- Environment: `main`
- App: `stable-modal-comfy-v2-diagnosis`
- Class: `ModalRuntimeEntrypointV2`
- Image: `im-2yVx6w2IIItdRJaNW2LosL`
- GPU: RTX PRO 6000

All four reported runs used that image, the same workflow hash, unique Modal task IDs, and fresh restore sessions.

| Run | Total wall | Submit to entry / TTExec | Remote execution | Pre-sampler | CLIP encode | Sampler |
|---|---:|---:|---:|---:|---:|---:|
| 1 | 122.06s | 93.64s | 28.33s | 20.37s | 2.80s | 3.73s |
| 2 | 31.65s | 4.82s | 26.73s | 19.87s | 6.83s | 3.73s |
| 3 | 75.38s | 39.54s | 35.74s | 29.05s | 6.98s | 3.73s |
| 4 | 31.95s | 5.48s | 26.38s | 19.45s | 6.56s | 3.73s |

Artifacts:

- `C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\comfymodal-data\benchmarks\runs\2026-07-19_12-09-54`
- `C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\comfymodal-data\benchmarks\runs\2026-07-19_12-13-15`

### Established findings

1. The 14–15 second execution target was not reached. The representative low-queue runs executed in `26.38–26.73s` with total wall of `31.65–31.95s`.
2. Certificate-gated preflight worked. Run 1 was a certificate miss with `4.29s` preflight; runs 2–4 recorded `cert_hit=true`, `preflight_skip=true`, and `preflight_ran=false`.
3. Certificate-hit healthy runs still spent `7.37–7.54s` between `graph_execution_start` and `prompt_executor_start`. The certificate's synchronous Modal Volume read path—especially `volume.reload()`—is the leading uninstrumented candidate. This is not yet causally proven.
4. Execution CLIP prefill did not activate. Every run emitted `execution_prefill_skip` with `reason=no_eligible_entries`, `total=1`, and `skipped=1`. One exact CLIP encode exists, but it lacks a `positive` or `negative` role and is rejected by the `critical` lane.
5. Runtime CLIP encode remained `6.56–6.98s` on certificate-hit runs. This is now the largest directly measured optimization opportunity.
6. UNET and CLIP graph waits were approximately `0.01ms`; model loading is not the current critical-path problem.
7. Sampler remained stable at `3.728–3.732s`; VAE decode was `0.39–0.48s`; post-sampler was `1.57–1.78s`.
8. Runs 1 and 3 contained Modal scheduling outliers of `93.64s` and `39.54s`. These are separate from application execution.
9. Healthy TTExec was `4.82–5.48s`, slightly above the desired 3–4 seconds but far smaller than the execution deficit.

### Prioritized next work

#### 1. Instrument and remove certificate-volume lookup latency

Measure these operations separately inside `_read_v2_validation_certificate`:

- `volume.reload()`
- `volume.exists()`
- `volume.read_bytes()`
- JSON decode
- component validation

Then perform a controlled candidate test that omits per-request `volume.reload()` and directly reads the mounted certificate. It must preserve fail-closed behavior on any missing, malformed, stale, or mismatched certificate.

Expected opportunity: approximately `7s` on certificate-hit execution if the lookup hypothesis is confirmed.

#### 2. Activate exact execution-phase CLIP prefill

First run a controlled `lane=all` experiment for this workflow's single statically resolved encode. Require:

- exactly one `execution_prefill_scheduled` event;
- exactly one `execution_prefill_completed` event;
- no UNET/CLIP loading overlap with encode;
- graph-visible CLIP encode/prefill wait below `200ms`;
- conditioning/output equivalence with the normal encode path.

If successful, implement graph-topology role inference so encodes connected to sampler positive/negative inputs qualify under `critical`, instead of globally retaining `all`.

Expected opportunity: approximately `6.5–7s`.

#### 3. Rebenchmark the combined candidate

Run one establishment request followed by four verified cold certificate-hit runs with 60-second gaps. Acceptance remains:

- TTExec does not regress;
- execution median at or below `15s`;
- total wall median at or below `20–21s` excluding clearly reported Modal scheduling outliers;
- no duplicate prefill, loader races, fallbacks, or output differences.

Current representative execution is approximately `26.5s`. Removing the suspected `~7s` certificate-volume synchronization and `~6.7s` graph-time CLIP encode would produce an estimated `~12.8s` before normal variance, making the 14–15 second target plausible.
