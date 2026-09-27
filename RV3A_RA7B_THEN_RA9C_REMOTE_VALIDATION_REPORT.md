# RV3A — RA7B then RA9C Remote Validation

## Status

- **RA7B functional verdict: PASS.** Six of six eligible true-cold requests were
  valid on the frozen `ra7b-step1-main-0831` deployment.
- **RA9C QD4 performance verdict: NOT ACCEPTED / PAUSED.** The dispatcher smoke
  selected the dispatcher arm, then failed closed during CLIP source cleanup.
  No dispatcher performance cohort was counted.

## RA7B acceptance

The accepted requests used `COMFYMODAL_OUTPUT_DURABILITY=off` semantics:
`result_ready` was the endpoint, encoded output bytes were observed, durability
was `NOT RUN`, `reopen_verified=false`, and seriality violations were zero.
CLIP remained BF16; QD transport remained legacy; cast-once was not enabled.

Golden-call walls (ms), including slow valid outliers:

`11459.278, 14136.007, 16503.562, 26203.608, 23280.430, 13131.917`

Sampling stayed approximately `5431–5671 ms`. The slow tails were upstream
hydration: CLIP load reached `10380 ms` and UNET load reached `7123 ms`; the
slowest calls were not sampling regressions.

The configured expected output SHA differed from the observed output SHA and
was retained as a warning under the current acceptance policy. All attempts,
including slow runs, remain in the RA7B evidence directory.

## Retained failures

1. Snapshot platform DNF: after snapshot creation, Modal failed to create the
   gofer process because `nvidia-container-cli` reported `driver rpc error:
   timed out`; runner exit code `128`. This is retained and excluded from the
   valid cohort.
2. RA9C control-plane source-probe timeout and stale/mismatched preliminary
   app attempts are retained and excluded.
3. Dispatcher smoke at
   `artifacts/phase_p1_serial_golden_v1/cohort_2026-08-31_18-22-24_1601fe/`
   was true-cold but invalid: `source worker did not stop within bounded
   cleanup`, followed by stale lease-generation secondary errors. It reached
   QD4 and recorded `4623.078 ms` producer-capacity blocking, but produced no
   valid Golden result.

## RA9C disposition

The dispatcher selector was wired through the deploy environment and verified
by the failed smoke's `qd_transport_arm=dispatcher` identity. The cleanup fix
was implemented locally and committed as `6b90e20`; focused tests passed.

The required QD4 questions—good-case load reduction and, more importantly, tail
variance suppression—remain unanswered. They require a fresh receipt-bound
smoke followed by the prescribed serial cohort after the fix.

## Reproducibility

- Source bundle: `my-repo.bundle`
- Current commit: `6b90e20`
- RA7B evidence: `RA7B_REMOTE_STEP1_EVIDENCE_20260831T000000Z/`
- RA9C evidence: `RA9C_REMOTE_EVIDENCE_20260831T000000Z/`
- QD4 source arms: `ra9c-control-0831` and `ra9c-dispatcher-0831`
