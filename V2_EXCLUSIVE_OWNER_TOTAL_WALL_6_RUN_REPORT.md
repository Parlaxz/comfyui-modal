# V2 Exclusive-Owner Total-Wall Validation — Six-Run Report

> Shadow deployment only. Best-case production candidate: `COMFYMODAL_V2_UNET_EXCLUSIVE_OWNER=1`, rehoming OFF, all page-path/synthetic-H2D/backing-verify/pretouch/quiesced/variance/host/full-trace diagnostics OFF, provider and region unpinned, single-use containers, minimal teardown.

## Protocol

- One clean shadow app deployed on `main`.
- Container env assertion (remote `run_env_probe`) before any measured run; study aborts on any gate mismatch.
- Snapshot-build request and the immediately following request excluded.
- Target: **6 valid cold single-use runs**; max 8 post-deploy attempts; 25.0 s gaps.
- Stop immediately on exit-139 / snapshot fallback / stream loss / duplicate migration / incorrect output / ownership-invariant failure.

## Container env assertion

**PASSED** — every gate below was read from the deployed container (`run_env_probe`), not assumed from the deploy script:

| Gate | Effective (container) |
|---|---|
| `COMFYMODAL_V2_UNET_EXCLUSIVE_OWNER` | `1` |
| `COMFYMODAL_V2_UNET_REHOME_AFTER_RESTORE` | `0` |
| `COMFYMODAL_V2_PAGE_PATH_PROBE` | `0` |
| `COMFYMODAL_V2_SYNTH_H2D_PROBE` | `0` |
| `COMFYMODAL_V2_UNET_BACKING_VERIFY` | `0` |
| `COMFYMODAL_V2_UNET_PRETOUCH` | `0` |
| `COMFYMODAL_V2_UNET_QUIESCED_TRANSFER` | `(absent/empty)` |
| `COMFYMODAL_V2_VARIANCE_DIAGNOSTICS` | `0` |
| `COMFYMODAL_V2_HOST_DIAGNOSTICS` | `0` |
| `COMFYMODAL_V2_FULL_TRACE` | `0` |
| `COMFYMODAL_V2_CLOUD` | `(absent/empty)` |
| `COMFYMODAL_V2_REGION` | `(absent/empty)` |

- min_containers=`0`, scaledown_window=`4`, single_use_containers=`True`

## Every attempt (preserved)

| attempt | class | cmd->resp (ms) | restore (ms) | join wait (ms) | worker term | join outcome | migrations | graph load wall (ms) | output |
|---|---|---:|---:|---:|---|---|---:|---:|---|
| attempt_0000.json | SKIP | 72,794.1 | 533.2 | - |  | - | 0 | 1,585.6 | OK |
| attempt_0001.json | SKIP | 42,090.5 | 1,753.5 | 997.7 | ready | ready,ready | 1 | 3.3 | OK |
| attempt_0002.json | cold | 22,479.3 | 423.4 | 9,614.8 | ready | ready,ready | 1 | 2.7 | OK |
| attempt_0003.json | cold | 18,320.5 | 1,474.5 | 681.0 | ready | ready,ready | 1 | 2.7 | OK |
| attempt_0004.json | cold | 23,720.2 | 376.4 | 7,136.4 | ready | ready,ready | 1 | 3.4 | OK |
| attempt_0005.json | cold | 47,049.6 | 421.5 | 946.6 | ready | ready,ready | 1 | 2.6 | OK |
| attempt_0006.json | cold | 30,946.9 | 3,904.5 | 1,029.9 | ready | ready,ready | 1 | 5.8 | OK |
| attempt_0007.json | cold | 31,374.9 | 721.0 | 4,063.9 | ready | ready,ready | 1 | 3.6 | OK |

## Six-run distribution (valid cold runs)

| metric | count | min | median | p90 | max |
|---|---:|---:|---:|---:|---:|
| command -> response (primary) | 6 | 18320.5 | 27333.6 | 47049.6 | 47049.6 |
| local preparation | 6 | 0.2 | 0.3 | 0.9 | 0.9 |
| modal handle and submission | 6 | 5.0 | 5.5 | 8.0 | 8.0 |
| command -> Python restore start (pre-Python Modal scheduling) | 6 | 4385.5 | 9457.2 | 38306.4 | 38306.4 |
| restore | 6 | 376.4 | 572.2 | 3904.5 | 3904.5 |
| restore end -> method entry | 6 | 13.9 | 20.4 | 95.7 | 95.7 |
| method entry -> UNET ownership claim (concurrent) | 6 | 340.3 | 697.0 | 1263.7 | 1263.7 |
| UNET claim -> ready (concurrent) | 6 | 1145.0 | 6503.3 | 10181.1 | 10181.1 |
| sampler graph-join wait | 6 | 681.0 | 2546.9 | 9614.8 | 9614.8 |
| sampling | 6 | 4940.7 | 5026.5 | 5270.6 | 5270.6 |
| VAE | 6 | 379.7 | 390.4 | 416.2 | 416.2 |
| output persistence | 6 | 591.8 | 601.2 | 606.0 | 606.0 |
| total accounted | 6 | 18403.8 | 27416.0 | 47134.0 | 47134.0 |
| remaining residual | 6 | -84.4 | -83.1 | 1.2 | 1.2 |

## Stage attribution per valid run (ms)

| attempt | local preparation | modal handle and submission | command -> Python restore start (pre-Python Modal scheduling) | restore | restore end -> method entry | method entry -> UNET ownership claim (concurrent) | UNET claim -> ready (worker load, concurrent) | remote method setup | PromptExecutor/cache setup | first node to CLIP | CLIP to sampler node | sampler graph-join wait | sampler node to sampling | sampling | post-sampling transition | VAE | output persistence | remote result handoff | remote/local return | total | residual |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| attempt_0002.json | 0.4 | 5.0 | 4,385.5 | 423.4 | 13.9 | 595.1 | 10,181.1 | 175.7 | 367.7 | 75.2 | 543.0 | 9,614.8 | 103.1 | 5,013.8 | 840.5 | 384.8 | 602.7 | - | 12.8 | 22,562.3 | -82.9 |
| attempt_0003.json | 0.3 | 8.0 | 7,660.1 | 1,474.5 | 23.1 | 1,020.5 | 1,228.5 | 979.2 | 426.8 | 69.1 | 93.1 | 681.0 | 89.5 | 5,022.8 | 881.2 | 379.7 | 601.3 | - | 14.0 | 18,403.8 | -83.3 |
| attempt_0004.json | 0.2 | 5.0 | 7,195.1 | 376.4 | 17.6 | 405.9 | 8,889.6 | 331.0 | 480.2 | 800.1 | 548.3 | 7,136.4 | 104.3 | 4,940.7 | 866.1 | 396.0 | 591.8 | - | 15.0 | 23,804.0 | -83.9 |
| attempt_0005.json | 0.8 | 5.0 | 38,306.4 | 421.5 | 15.0 | 340.3 | 1,145.0 | 117.9 | 266.9 | 55.3 | 98.8 | 946.6 | 96.9 | 5,030.1 | 765.8 | 396.6 | 597.5 | - | 13.0 | 47,134.0 | -84.4 |
| attempt_0006.json | 0.9 | 7.0 | 14,623.7 | 3,904.5 | 95.7 | 1,263.7 | 4,116.9 | 1,239.2 | 2,970.5 | 69.8 | 71.5 | 1,029.9 | 94.2 | 5,136.4 | 750.3 | 416.2 | 606.0 | - | 12.5 | 31,028.1 | -81.2 |
| attempt_0007.json | 0.3 | 6.0 | 11,254.2 | 721.0 | 71.8 | 799.0 | 9,382.0 | 597.4 | 1,130.4 | 144.6 | 4,244.8 | 4,063.9 | 148.3 | 5,270.6 | 896.3 | 380.7 | 601.1 | 1,829.2 | 13.0 | 31,373.7 | 1.2 |

## Per-run acceptance checks (valid cold runs)

| attempt | <13000 ms | 1 migration | worker ready | join ready | cache-only graph load | no fallback | no sampler-absent-pending | no cancelled worker | output correct | residual <=100 ms |
|---|---|---|---|---|---|---|---|---|---|---|
| attempt_0002.json | N | Y | Y | Y | Y | Y | Y | Y | Y | Y |
| attempt_0003.json | N | Y | Y | Y | Y | Y | Y | Y | Y | Y |
| attempt_0004.json | N | Y | Y | Y | Y | Y | Y | Y | Y | Y |
| attempt_0005.json | N | Y | Y | Y | Y | Y | Y | Y | Y | Y |
| attempt_0006.json | N | Y | Y | Y | Y | Y | Y | Y | Y | Y |
| attempt_0007.json | N | Y | Y | Y | Y | Y | Y | Y | Y | Y |

## Pass / fail conclusion

- Valid cold runs collected: **6** / 6
- command->response distribution: min 18320.5 ms, median 30946.9 ms, max 47049.6 ms; all < 13000 ms: no
- Failures:
  - command->response >= 13000 ms on 6 run(s)

**FAIL** — the current best production candidate does **not** deliver command
submission → durable response under 13.0 s on any of the six valid cold runs
(18.3–47.0 s).  All ownership/robustness invariants pass on every run (exactly
one migration, worker terminal `ready`, graph join `ready`, graph load reduced
to cache validation only at 2.6–5.8 ms, zero fallback, zero sampler-absent-
while-pending, zero cancelled worker, output correct, residual ≤ 100 ms), and
there were no crashes or snapshot fallbacks.  The waterfall correction is
complete: pre-Python Modal scheduling and the sampler graph-join wait are now
explicit stages, and the reconciliation residual is −84.4…+1.2 ms on every run
(accounted slightly exceeds the wall on 5/6 runs because the concurrent worker
span is reported but excluded from the sequential total; the absolute residual
is within the ≤ 100 ms acceptance bound).

**Exact remaining stage.**  With the waterfall corrected, the wall is
attributed as follows (median over the 6 valid runs):

| stage | median (ms) | share of total |
|---|---:|---:|
| command → Python restore start (pre-Python Modal scheduling) | 9,457 | 31% |
| sampler graph-join wait (worker UNET load tail) | 2,547 | 8% |
| sampling | 5,027 | 16% |
| restore | 572 | 2% |
| UNET claim → ready (concurrent worker span, reported) | 6,503 | — |
| all other stages (method setup, CLIP, VAE, output, return, local) | ~3,200 | ~10% |

The single dominant stage is **pre-Python Modal scheduling** (submission →
`remote_python_resume`), 4,386–38,306 ms with median 9,457 ms — i.e., the
unpinned pool's cold-container scheduling/snapshot-restore staging before
Python resumes.  It alone exceeds the 13 s budget on the slowest runs
(38,306 ms on attempt_0005).  The second-largest controllable stage is the
**sampler graph-join wait** (the sampler waits for the worker's restored-page
UNET load: 681–9,615 ms).  Both are now explicit waterfall stages rather than
residual.  No further optimization was implemented during this study; this run
only establishes the clean baseline and the exact remaining stage.

## Files changed

- `comfymodal_runtime/v2_waterfall.py` — explicit waterfall stages (sampler graph-join wait; method-entry→claim and claim→ready as concurrent rows; pre-Python Modal scheduling labeled), residual ≤ 100 ms on every run.
- `comfymodal_runtime/modal_app.py` — `run_env_probe` shadow method (container env assertion); `_runtime_env` now propagates `COMFYMODAL_V2_SINGLE_USE_CONTAINERS` (was silently dropped from the container env mirror).
- `tools/run_ownership_rehoming_study.py` — container env assertion before any measured run (abort on mismatch); abort on ownership-invariant/output failures; per-run total-wall stage metrics; six-run report writer + offline `render-report` mode.
- `deploy_and_run_ownership_rehoming.py` — `total-wall` shadow app mode (exclusive owner ON, unpinned, all heavy diagnostics OFF).
- `tests/test_v2_waterfall.py` — expected stage list updated for the new explicit stages.

Final commit SHA: `5840f27c3309063e367bcc5b5d95742ebc8b6c73`
