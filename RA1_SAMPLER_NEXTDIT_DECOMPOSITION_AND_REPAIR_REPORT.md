# RA1 Sampler / NextDiT Decomposition Report

## Decision

RA1 is accepted. Three separate serial observations on deployment
`07d2f9ee416440d7e36be2699f718b1d305f10e1f6abc970f3c544be5c9eb359` passed the
Golden contract and the RA1 diagnostic gates. No sampler-semantic or output
changing repair was applied; the implementation changes are measurement-only.

## Accepted observations

| Observation | Cohort | Golden result | Sampling window | Profile | Residual |
|---|---|---|---:|---|---:|
| 1 | `cohort_2026-08-29_07-04-45_e2294c` | valid / true-cold / exact SHA | 6401.144 ms | 8 steps, 17 evals, 10/7 | 5.490 ms |
| 2 | `cohort_2026-08-29_07-07-46_ce93a9` | valid / true-cold / exact SHA | 5899.185 ms | 8 steps, 17 evals, 10/7 | 4.240 ms |
| 3 | `cohort_2026-08-29_07-09-47_144216` | valid / true-cold / exact SHA | 5980.058 ms | 8 steps, 17 evals, 10/7 | 4.981 ms |

Sampling-window summary: mean `6093.462 ms`, median `5980.058 ms`, min/max
`5899.185/6401.144 ms`, range `501.959 ms`, sample SD `269.511 ms`, CV
`4.423%`. A p90 is intentionally not reported for n=3.

## Decomposition findings

- CacheDiT was discoverable, attached, enabled, and matched the pinned
  `call_count=17`, `compute_count=10`, `skip_count=7` contract in every accepted
  observation.
- NextDiT category measurements were captured for embeddings, refiner, norm,
  attention, MLP, and output across all real evaluations.
- Attention dispatch consistently showed a Sage override closure falling back
  to ComfyUI `attention_pytorch`; the shared SDPA seam observed PyTorch SDPA
  calls. This is reported as runtime fallback evidence, not as fused Sage
  execution.
- Host monotonic timing and CUDA event timing were captured without CUDA
  synchronization inside the authoritative sampling window. The single CUDA
  realization occurred after `sampling_end`.
- All three artifacts report residual status `ok`; exact output SHA is
  `454dbda2939f4abadabd8ca6c524d3a615f384ce19873faf5adaf4693c1848da`.

## Evidence

- Deployment: `.v2ctl/deployments/deploy_20260829-020412_07d2f9ee.json`
- Observation 1: `artifacts/phase_p1_serial_golden_v1/cohort_2026-08-29_07-04-45_e2294c/`
- Observation 2: `artifacts/phase_p1_serial_golden_v1/cohort_2026-08-29_07-07-46_ce93a9/`
- Observation 3: `artifacts/phase_p1_serial_golden_v1/cohort_2026-08-29_07-09-47_144216/`

## Follow-up gate

RA2 has not started. The `golden_p1` profile currently carries the temporary
RA1 `COMFYMODAL_SAMPLING_DEEP_PROFILE=blocks` setting; redeploy a clean,
measurement-appropriate profile before any RA2 snapshot/restore experiment.
