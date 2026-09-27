# C9 Recovery — All Recorded Samples

This report lists every recorded C9 run sample from the preserved `07b`
attempts and the corrected `07c` campaign. No sample has been deleted. The
`07b` and superseded `07c` rows are retained as **NON-DECISION** evidence.

## Run samples

| # | Evidence root / candidate | Observation | Role | QD | C9 total wall (ms) | Physical read span (ms) | Result / disposition | Error or notes |
|---:|---|---:|---|---:|---:|---:|---|---|
| 1 | [`07b/smoke_a`](../07b_c9_faithful_recovery/smoke_a/runs/20260905T043455_b7629d67_c9_o01_unet_qd8.json) | 1 | UNET | 8 | — | — | DNF; non-decision | `c9_block_bytes_not_enforced`; wrong wrapper path |
| 2 | [`07b/smoke_a`](../07b_c9_faithful_recovery/smoke_a/runs/20260905T043455_b7629d67_c9_o02_unet_qd8.json) | 2 | UNET | 8 | — | — | DNF; non-decision | `c9_block_bytes_not_enforced`; wrong wrapper path |
| 3 | [`07b/smoke_a_retry`](../07b_c9_faithful_recovery/smoke_a_retry/runs/20260905T043710_834d26a8_c9_o01_unet_qd8.json) | 1 | UNET | 8 | — | — | DNF; non-decision | No NVIDIA driver; observed CPU 21 rather than required 12 |
| 4 | [`07b/smoke_a_retry`](../07b_c9_faithful_recovery/smoke_a_retry/runs/20260905T043710_834d26a8_c9_o02_unet_qd8.json) | 2 | UNET | 8 | — | — | DNF; non-decision | No NVIDIA driver; observed CPU 21 rather than required 12 |
| 5 | [`07b/smoke_a_mlock`](../07b_c9_faithful_recovery/smoke_a_mlock/runs/20260905T045259_81f99b8f_c9_o01_unet_qd8.json) | 1 | UNET | 8 | — | — | DNF; non-decision | Wrong pinning mechanism: explicit `mlock:12:Cannot allocate memory` |
| 6 | [`07b/smoke_a_mlock`](../07b_c9_faithful_recovery/smoke_a_mlock/runs/20260905T045259_81f99b8f_c9_o02_unet_qd8.json) | 2 | UNET | 8 | — | — | DNF; non-decision | Wrong pinning mechanism: explicit `mlock:12:Cannot allocate memory` |
| 7 | [`07c/smoke_a`](smoke_a/runs/20260905T052549_22e97645_c9_o01_unet_qd8.json) | 1 | UNET | 8 | 4255.091605 | 1833.648988 | Structurally valid; non-decision | Sequential pre-thread pinned allocations |
| 8 | [`07c/smoke_a`](smoke_a/runs/20260905T052549_22e97645_c9_o02_unet_qd8.json) | 2 | UNET | 8 | 4603.728789 | 2691.038048 | Structurally valid; non-decision | Sequential pre-thread pinned allocations |
| 9 | [`07c/smoke_a_worker_local`](smoke_a_worker_local/runs/20260905T054026_2577d855_c9_o01_unet_qd8.json) | 1 | UNET | 8 | 5745.413492 | 2257.287294 | Structurally valid; non-decision | Worker-local allocation; Torch import still timed |
| 10 | [`07c/smoke_a_worker_local`](smoke_a_worker_local/runs/20260905T054026_2577d855_c9_o02_unet_qd8.json) | 2 | UNET | 8 | 5431.591480 | 2419.829326 | Structurally valid; non-decision | Worker-local allocation; Torch import still timed |
| 11 | [`07c/smoke_a_preimport`](smoke_a_preimport/runs/20260905T054931_2e4786b4_c9_o01_unet_qd8.json) | 1 | UNET | 8 | 2208.007169 | 1960.468954 | Structurally valid; audit-needed | Torch import moved outside C9 timer |
| 12 | [`07c/smoke_a_preimport`](smoke_a_preimport/runs/20260905T054931_2e4786b4_c9_o02_unet_qd8.json) | 2 | UNET | 8 | 2676.590596 | 2414.925844 | Structurally valid; audit-needed | Torch import moved outside C9 timer |
| 13 | [`07c/smoke_a_final`](smoke_a_final/runs/20260905T060858_0998a3f2_c9_o01_unet_qd8.json) | 1 | UNET | 8 | 2279.125368 | 2008.555738 | Runtime valid; validator-invalid | Stale validator required removed `effective_GBps` |
| 14 | [`07c/smoke_a_final`](smoke_a_final/runs/20260905T060858_0998a3f2_c9_o02_unet_qd8.json) | 2 | UNET | 8 | 2764.867667 | 2524.711549 | Runtime valid; validator-invalid | Stale validator required removed `effective_GBps` |
| 15 | [`07c/smoke_a_validated`](smoke_a_validated/runs/20260905T061248_f7fc4cbf_c9_o01_unet_qd8.json) | 1 | UNET | 8 | 2161.543330 | 1883.353444 | Validated; audit-needed | Canonical `effective_gbps`; final authoritative Smoke A |
| 16 | [`07c/smoke_a_validated`](smoke_a_validated/runs/20260905T061248_f7fc4cbf_c9_o02_unet_qd8.json) | 2 | UNET | 8 | 2177.490273 | 1950.261862 | Validated; audit-needed | Canonical `effective_gbps`; final authoritative Smoke A |

## Pinning capability samples

Each capability receipt is a separate no-model-read/no-H2D call that allocated
eight 32 MiB Torch tensors. Every receipt below reports 8/8
`is_pinned == true` on RTX PRO-6000, CPU12, Testing 7.

| Receipt | Torch | CUDA build | Device | Buffers | Status | Model read | H2D pipeline |
|---|---|---|---|---:|---|---|---|
| [`pinning_capability_receipt.json`](pinning_capability_receipt.json) | 2.14.0+cu130 | 13.0 | NVIDIA RTX PRO 6000 Blackwell Server Edition | 8/8 pinned | PASS | false | false |
| [`pinning_capability_receipt_worker_local.json`](pinning_capability_receipt_worker_local.json) | 2.14.0+cu130 | 13.0 | NVIDIA RTX PRO 6000 Blackwell Server Edition | 8/8 pinned | PASS | false | false |
| [`pinning_capability_receipt_preimport.json`](pinning_capability_receipt_preimport.json) | 2.14.0+cu130 | 13.0 | NVIDIA RTX PRO 6000 Blackwell Server Edition | 8/8 pinned | PASS | false | false |
| [`pinning_capability_receipt_final.json`](pinning_capability_receipt_final.json) | 2.14.0+cu130 | 13.0 | NVIDIA RTX PRO 6000 Blackwell Server Edition | 8/8 pinned | PASS | false | false |

## Final interpretation

The authoritative final Smoke A median is **2169.516802 ms**. It is about
**569.517 ms slower** than the approximately 1.6 s historical UNET source
class. Smoke B and the 36-observation final cohort were not run because the
two QD8 totals remained in the required 2–3 second audit band.

The corrected path uses Torch pinned allocation, worker-local reusable buffers,
one shared FD, static disjoint ranges, positioned `preadv`, and no H2D. The
remaining difference is not assigned to an individual component without a
controlled one-variable A/B.
