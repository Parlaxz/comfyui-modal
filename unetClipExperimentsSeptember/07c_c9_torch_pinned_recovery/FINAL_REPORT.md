# C9 Torch-Pinned Recovery — Final Decision Report

## Decision

The corrected combined C9 mechanism is structurally valid and materially
better than the wrong candidates, but the campaign is **STOPPED before Smoke B
and before the final cohort**. The two authoritative validated Smoke A runs
remain in the required 2–3 second audit band and do not establish recovery to
the historical approximately 1.6 s UNET source class.

## Required answers

1. **Torch pinned allocation on Modal:** yes. Smoke 0 succeeded on Testing
   7/main with Torch `2.14.0+cu130`, CUDA available, and
   `NVIDIA RTX PRO 6000 Blackwell Server Edition`.
2. **Every worker pinned:** yes. Smoke 0 proved 8/8 32 MiB tensors with
   `is_pinned == true`; Smoke A worker evidence also proves all 8/8.
3. **Smoke A QD8 C9 totals:** `2161.543330 ms` and `2177.490273 ms`.
4. **Smoke B QD2/QD4/QD8:** not run; the Smoke A audit gate did not pass.
5. **QD8 recovery:** partial. It escaped the 5.4–5.7 s import/worker-start
   regression and is mechanically sane, but did not reach the historical
   target class.
6. **Beat approximately 1.6 s UNET class:** no. The two-run median is
   `2169.516802 ms`, approximately `569.517 ms` above 1.6 s.
7. **Final six-run medians:** not applicable; the 36-observation cohort was
   not run.
8. **Distance from historical C9:** the validated QD8 C9 median is about 2.17
   s versus the approximately 1.6 s historical UNET source class. The
   physical-read spans were `1883.353444 ms` and `1950.261862 ms` (median
   `1916.807653 ms`). The remaining difference is unresolved between provider/
   volume behavior and historical environment details; no component win is
   claimed.
9. **Next single difference to isolate:** add/remove exactly one transport
   variable in a new controlled A/B. The highest-value next candidate is the
   physical source substrate/provider path, while retaining this exact Torch
   pinned/shared-FD/static-range worker loop as the control. Do not alter
   multiple mechanics at once.

## Evidence authority

- Deployment: `deployment_manifest.json`;
- Pinning: `pinning_capability_receipt_final.json` and
  `pinning_capability_receipt_preimport.json`;
- Validated Smoke A ledger:
  `smoke_a_validated/ledger.json`;
- Validated Smoke A raw runs:
  `smoke_a_validated/runs/20260905T061248_f7fc4cbf_c9_o01_unet_qd8.json` and
  `...c9_o02_unet_qd8.json`;
- Prior failed/invalid attempts remain preserved under this root and under
  `07b_c9_faithful_recovery`.

No H2D pipeline, CUDA copy, model construction, or full cohort was performed.
