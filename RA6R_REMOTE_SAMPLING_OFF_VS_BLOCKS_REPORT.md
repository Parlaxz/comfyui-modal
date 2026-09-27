# RA6R Remote Sampling: OFF vs BLOCKS

## Decision

`RA6_REMOTE_BLOCKED_EXACT_SOURCE_REPRODUCTION`

The requested A/B was not run. The selector is **DEPLOYMENT_ONLY**, not
request-selectable. The frozen RV2B deployment has `off` baked into its
deployment environment. No authoritative immutable RV2B source/artifact
receipt exists from which a matching `blocks` deployment can be made without
capturing or copying the concurrently mutating worktree. The experiment is
therefore stopped rather than weakened.

No source, configuration, test, or skill implementation was changed. No
deployment or Golden request was performed by RA6R. The two RA6R reports are
the only new files created by this lane.

## Scope determination

| Check | Result | Evidence |
|---|---|---|
| Selector | `COMFYMODAL_SAMPLING_DEEP_PROFILE` | `config/v2/flag_registry.toml:236-244` |
| Lifecycle | `consumed_at=module_import`, `change_requires=deploy` | same registry entry |
| Request field | absent from `run_golden_serial_stream` request contract | `comfymodal_runtime/modal_app.py:21110-21188` |
| Runtime selection | process environment, then runtime state file; not request data | `comfymodal_runtime/sampling_deep_profile.py:246-265` |
| Modal boundary | value is projected into class/deployment environment | `comfymodal_runtime/modal_app.py:3581-3587` |
| RV2B effective value | `off` | frozen manifest and truth report |
| Selector scope | **`DEPLOYMENT_ONLY`** | source and lifecycle evidence above |

The supported `--set COMFYMODAL_SAMPLING_DEEP_PROFILE=blocks` path changes the
deployment. A runtime flag-file override is invalid under the stored
`runtime_override_policy=forbid` and cannot convert the deployed `off` value.

## Frozen RV2B identity

| Item | Value |
|---|---|
| App | `batch-rv2b-golden-measurement` |
| Target | `ModalRuntimeEntrypointV2.run_golden_serial_stream` |
| Modal deployment/version | `aaba80156dc559e591fc7379836991059f7ecc31b107875b0635de94e8ac9a48` |
| Deployment fingerprint | `3afb957ba2e1275eddca2be82b9dfe54fcf0b80c77f66d8fdab1478436d765d9` |
| Image | `im-kgisSW1st7TzVVWiuyOwvJ` |
| GPU / resources | `rtx-pro-6000`, 12 CPU, 32768 MB |
| Manifest | `.v2ctl/deployments/deploy_20260830-215842_3afb957b.json` |
| Effective profile | `COMFYMODAL_SAMPLING_DEEP_PROFILE=off` |
| Custom-node generation | `e4671089280ad6cc1558b1859baec58f6fa5f22e1ba74bdb6b8e55c208b7fa58` |

The manifest records `git_dirty=true` and local HEAD
`7f9a19ef9bf88c1424340897cdf723748b1341dc`; the current worktree contains
unrelated concurrent edits. The Modal version identity is not a local Git
object. The current host status also reports stored fingerprint
`3afb957b...` versus current fingerprint `ff22453a...`. These facts prevent
proving an exact source reproduction from this tree; local drift is not treated
as evidence that the remote deployment changed.

The existing one-off host admission principle can supply stored deployment/run
identity for the already-deployed surface, but it cannot change `off` to
`blocks`, and it cannot provide the missing immutable source for a new
diagnostic deployment.

## Cohorts and outcome

| Arm | Valid eligible runs | Deployment work | Result |
|---|---:|---:|---|
| OFF | 5, inherited from RV2B | 0 by RA6R | valid true-cold same-deployment baseline |
| BLOCKS | 0 | 0 | not run; exact-source stop |
| STEPS | 0 | 0 | intentionally not run |

`EXISTING_RV2B_DEPLOYMENT_REUSED=NO` means no RA6R request reused it. The five
OFF observations remain usable as the pre-existing RV2B baseline, not as new
RA6R measurements. `SAME_SOURCE_AB=NO` because no two-arm comparison was
executed.

## Authoritative OFF baseline

The only accepted RA6R-comparable wall currently available is the existing
full `golden_sampling` stage, from `sampling_start` through `sampling_end`.
It is **TOTAL**. Progress-loop fields and inner profiler fields are not
substitutes for it.

| Run | Authoritative `golden_sampling` wall (ms) |
|---:|---:|
| 1 | 5689.258 |
| 2 | 5253.376 |
| 3 | 5619.835 |
| 4 | 5463.582 |
| 5 | 5585.380 |

OFF statistics: min `5253.376 ms`, median `5585.380 ms`, max `5689.258 ms`,
range `435.882 ms`, sample CV `0.031`.

BLOCKS distribution, absolute delta, percentage delta, and profiler tax are
**UNPROVEN**. No inner timer was compared against OFF.

## Sampling decomposition status

No current RA6R BLOCKS payload exists. Consequently, the following required
current-run quantities are not asserted:

* authoritative BLOCKS start/end, visible loop boundaries, pre-first-step,
  post-loop, final-eval placement, and residual;
* current first-eval and first-compute premiums;
* current attention, norm/gate/residual, MLP, modulation, embedding/output,
  CacheDiT/controller, solver/controller, callback, and gap contributions;
* current attention fraction, non-attention fraction, and next optimization
  target.

The historical RA6H blocks artifacts are context only, not current A/B
evidence. They report three different deployment lineage observations with
authoritative walls `4917.454`, `4882.541`, and `4905.120 ms`; direct attention
was `728.183`, `724.770`, and `728.644 ms`. Those nested category values imply
an approximately 15% **historical arithmetic ceiling**, not a current RA6R
measurement or speedup promise. The historical `norm_gate_residual` bucket is
derived and is not additive.

The existing pinned CacheDiT contract is retained as a baseline invariant:

```text
17 evaluations = 10 COMPUTE + 7 SKIP; 0 fallback
```

This is documented by RV2B/RA1 evidence, but it was not separately verified
for a RA6R BLOCKS request because no such request occurred. No current
first-use premium, sampler residual, or residency causal claim can be made.

## Opportunity ranking status

The requested current ranking cannot be established without the missing BLOCKS
arm. Historical evidence suggests first-use/setup and later transformer work
are materially sized, attention has a roughly 15% ceiling, skips are cheap,
and post-loop teardown is small; these are not interchangeable current totals.

| Requested rank | Category | RA6R status |
|---:|---|---|
| 1 | first-use/setup | historical candidate only; current size/removability unknown |
| 2 | attention | historical ceiling only; current fraction unknown |
| 3 | non-attention transformer | current size unknown |
| 4 | CacheDiT/controller | invariant known; current outside-compute cost unknown |
| 5 | solver/controller/gaps | current ownership unknown |
| 6 | post-loop work | historical small; current value unknown |
| 7 | UNKNOWN residual | not measurable without BLOCKS |

`NEXT_SAMPLING_OPTIMIZATION_TARGET=UNPROVEN_PENDING_CLEAN_PINNED_BLOCKS_AB`.
No implementation recommendation is made from this blocked lane.

## Raw evidence

The complete pre-existing OFF evidence is retained in:

* `RV2B_REMOTE_GOLDEN_BASELINE_RAW_LOG.md` (complete campaign stream and
  pointers to manifests, event streams, summaries, and provenance);
* `RV2B_REMOTE_GOLDEN_BASELINE_TRUTH_REPORT.md`;
* `RV2B_REMOTE_MEASUREMENT_RAW_EVIDENCE_20260830T000000Z/`;
* `RV2B_REMOTE_MEASUREMENT_RAW_EVIDENCE_20260830T000000Z_REPLACEMENT2/`;
* `RV2B_REMOTE_MEASUREMENT_RAW_EVIDENCE_20260830T000000Z_REPLACEMENT3/`;
* the five eligible cohort artifact directories listed in the raw log.

Historical full profiler payload references are retained by
`RA6H_HISTORICAL_SAMPLING_FIRST_USE_FORENSICS_REPORT.md` and its cited
`REAL_CLIP_CACHE_MISS_REPORT.md` artifacts. No RA6R BLOCKS payload was produced
or discarded.

```text
RA6_REMOTE_BLOCKED_EXACT_SOURCE_REPRODUCTION
RA6R_COMPLETE=NO
SOURCE_CODE_CHANGED=NO
CONFIG_SOURCE_CHANGED=NO
EXISTING_RV2B_DEPLOYMENT_REUSED=NO
SELECTOR_SCOPE=DEPLOYMENT_ONLY
DEPLOYMENTS_PERFORMED=0
OFF_VALID_RUNS=5
BLOCKS_VALID_RUNS=0
STEPS_RUNS=0
SAME_SOURCE_AB=NO
CACHE_DIT_EVALS=17 (existing OFF baseline; no BLOCKS run)
CACHE_DIT_COMPUTE=10 (existing OFF baseline; no BLOCKS run)
CACHE_DIT_SKIP=7 (existing OFF baseline; no BLOCKS run)
PROFILER_TAX=UNPROVEN
AUTHORITATIVE_OFF_MEDIAN_MS=5585.380
AUTHORITATIVE_BLOCKS_MEDIAN_MS=UNPROVEN
CURRENT_FIRST_EVAL_PREMIUM_MS=UNPROVEN
CURRENT_FIRST_COMPUTE_PREMIUM_MS=UNPROVEN
ATTENTION_FRACTION_OF_SAMPLING=UNPROVEN
NON_ATTENTION_FRACTION_OF_SAMPLING=UNPROVEN
SAMPLER_RESIDUAL_MS=UNPROVEN
NEXT_SAMPLING_OPTIMIZATION_TARGET=UNPROVEN_PENDING_CLEAN_PINNED_BLOCKS_AB
RAW_LOG_COMPLETE=YES
MODAL_CONTACTED=NO
REPORT=RA6R_REMOTE_SAMPLING_OFF_VS_BLOCKS_REPORT.md
RAW_LOG=RA6R_REMOTE_SAMPLING_RAW_LOG.md
```
