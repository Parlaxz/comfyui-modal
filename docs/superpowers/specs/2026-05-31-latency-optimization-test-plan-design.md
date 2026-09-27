# Latency Optimization Iteration Plan

Date: 2026-05-31

## Goal

Iteratively reduce ComfyUI Modal request latency for the existing Blackwell Flux2 workflow while preserving current cold-start and restore behavior.

Primary target:
- second-run `remote_total` under `9s`

Guardrail:
- keep startup / restore around the current `~3s` behavior

Hard constraint:
- no workflow changes during testing

## Fixed Test Conditions

Every round must keep these unchanged:

- same workflow JSON
- same sampler and scheduler
- same step count
- same prompt and negative prompt
- same seed
- same model files
- same resolution
- same deployment path and Modal batch file flow

Only one optimization idea may change per round.

## Required Metrics Per Round

For each deploy and test cycle, collect and paste:

1. startup / restore timing line
2. first-run `stage=remote_total`
3. second-run `stage=remote_total`
4. second-run node timings for:
   - `CLIPLoader`
   - `UNETLoader`
   - `SamplerCustomAdvanced`
   - `VAEDecode`
5. any backend or cache-specific log lines added by the round

These metrics are the only data used to decide whether to keep, refine, or revert an idea.

## Success Criteria

### Primary
- second-run `remote_total < 9s`

### Secondary
- startup / restore stays near baseline and does not regress materially
- no quality regressions
- no workflow changes
- no new runtime instability

## Optimization Strategy

The latency budget is split into two lanes:

1. **Non-sampler overhead**
   - repeated loader / object reconstruction / rematerialization work
2. **Sampler time**
   - actual denoise / inference work inside `SamplerCustomAdvanced`

The plan prioritizes non-sampler overhead first because current totals indicate sampler time alone is not enough to reach the `<9s` target.

## Round Structure

### Round 0 — Baseline Capture

Purpose:
- lock current measurements before new changes

Change set:
- none

Expected outcome:
- baseline reference for all later comparisons

Decision rule:
- do not proceed with interpretation until first-run and second-run values are captured from the same deploy

### Round 1 — Lazy One-Hot Live Loader-Object Reuse

Purpose:
- remove repeated second-run loader overhead without moving work into startup

Design:
- cache the live outputs of:
  - `UNETLoader`
  - `CLIPLoader` / `DualCLIPLoader`
  - `VAELoader`
- cache only one active stack
- reuse only on an exact stack match
- populate lazily after a real request
- do not preload at startup
- do not warm at restore
- evict and rebuild when stack changes

Why this approach:
- file-level caching already removed most raw disk read cost
- logs show repeated request-time model object creation and load behavior still exists
- lazy reuse preserves startup while targeting second-run latency directly

Expected result:
- second-run reduction from repeated loader / rematerialization work

Failure conditions:
- startup or restore regresses materially
- second-run does not improve meaningfully
- stale-object or cross-stack reuse bugs appear

### Round 2 — Conditioning Cache

Prerequisite:
- Round 1 is stable and keeps startup flat

Purpose:
- shave repeated CLIP text conditioning overhead for identical prompt inputs

Design:
- cache text-conditioning outputs keyed by the exact prompt text plus clip stack identity and relevant loader settings
- only reuse for exact matches

Expected result:
- modest but low-risk second-run improvement

Failure conditions:
- any prompt mismatch or stale-conditioning bug
- negligible gain compared with added complexity

### Round 3 — Inference Backend A/B

Prerequisite:
- overhead reductions are exhausted or insufficient

Purpose:
- reduce sampler time without changing workflow structure

Initial test matrix:
- baseline SDPA
- explicit Sage CUDA backend if viable in the deployed runtime

Rules:
- workflow remains identical
- only backend selection changes
- compare sampler node time and total second-run time

Expected result:
- reduction in `SamplerCustomAdvanced`

Failure conditions:
- no sampler win
- quality changes
- runtime instability

### Round 4 and Beyond — Data-Driven Follow-Up

If second-run overhead still dominates:
- refine live-object reuse
- tighten stack matching or reuse boundaries

If sampler time still dominates:
- continue runtime/backend experiments within the no-workflow-change rule

No future round may bundle unrelated changes.

## Decision Rules After Each Round

After each deploy:

- if startup regresses materially, revert that lane
- if second-run improves by less than about `0.5s`, deprioritize that lane
- if second-run improves materially and startup stays flat, keep the change and continue stacking wins
- if a change affects quality or stability, revert even if timing improves

## Logging Requirements

Each implementation round should add enough logging to prove whether the change actually executed. Examples:

- loader-object cache hit / miss
- stack key used for reuse
- backend selection line
- conditioning cache hit / miss

Logs must make it possible to distinguish:
- feature present but unused
- feature active and helping
- feature active but harmful

## Out of Scope

The following are excluded from this test plan:

- workflow edits
- sampler or scheduler changes
- prompt changes
- step-count changes
- quality-reducing shortcuts already rejected by testing
- NVFP4 as a test requirement

## Implementation Order Recommendation

1. baseline capture
2. lazy one-hot live loader-object reuse
3. conditioning cache
4. inference backend A/B

This order maximizes the chance of getting second-run total under `9s` without sacrificing startup behavior.
