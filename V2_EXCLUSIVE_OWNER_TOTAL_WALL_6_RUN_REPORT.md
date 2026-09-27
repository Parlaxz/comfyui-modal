# V2 Exclusive-Owner Total-Wall Validation — Six-Run Report

> Shadow deployment only. Best-case production candidate: `COMFYMODAL_V2_UNET_EXCLUSIVE_OWNER=1`, rehoming OFF, all page-path/synthetic-H2D/backing-verify/pretouch/quiesced/variance/host/full-trace diagnostics OFF, cloud=unpinned, region unpinned, single-use containers, minimal teardown.

## Protocol

- One clean shadow app deployed on `main`.
- Container env assertion (remote `run_env_probe`) before any measured run; study aborts on any gate mismatch.
- Snapshot-build request and the immediately following request excluded.
- Target: **3 valid cold single-use runs**; max 5 post-deploy attempts; 25.0 s gaps.
- Acceptance gate: command → response **< 13500 ms** on every run.
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
| attempt_0000.json | cold | 36,420.8 | 728.7 | 654.3 | ready | ready,ready | 1 | 3.1 | OK |
| attempt_0001.json | cold | 16,775.3 | 1,160.2 | 685.0 | ready | ready,ready | 1 | 2.8 | OK |

## Six-run distribution (valid cold runs)

| metric | count | min | median | p90 | max |
|---|---:|---:|---:|---:|---:|
| command -> response (primary) | 2 | 16775.3 | 26598.1 | 36420.8 | 36420.8 |
| local preparation | 2 | 0.6 | 0.7 | 0.8 | 0.8 |
| modal handle and submission | 2 | 6.0 | 7.8 | 9.5 | 9.5 |
| command -> Python restore start (pre-Python Modal scheduling) | 2 | 6805.7 | 14184.5 | 21563.3 | 21563.3 |
| restore | 2 | 728.7 | 944.4 | 1160.2 | 1160.2 |
| restore end -> method entry | 2 | 33.1 | 1746.6 | 3460.2 | 3460.2 |
| method entry -> UNET ownership claim (concurrent) | 2 | 826.1 | 1529.4 | 2232.6 | 2232.6 |
| UNET claim -> ready (concurrent) | 2 | 1184.4 | 1392.5 | 1600.7 | 1600.7 |
| sampler graph-join wait | 2 | 654.3 | 669.7 | 685.0 | 685.0 |
| sampling | 2 | 5004.6 | 5022.2 | 5039.7 | 5039.7 |
| VAE | 2 | 380.8 | 404.0 | 427.2 | 427.2 |
| output persistence | 2 | 593.8 | 597.3 | 600.8 | 600.8 |
| total accounted | 2 | 16960.4 | 26727.7 | 36495.0 | 36495.0 |
| remaining residual | 2 | -185.0 | -129.6 | -74.2 | -74.2 |

## Stage attribution per valid run (ms)

| attempt | local preparation | modal handle and submission | command -> Python restore start (pre-Python Modal scheduling) | restore | restore end -> method entry | method entry -> UNET ownership claim (concurrent) | UNET claim -> ready (worker load, concurrent) | remote method setup | PromptExecutor/cache setup | first node to CLIP | CLIP to sampler node | sampler graph-join wait | sampler node to sampling | sampling | post-sampling transition | VAE | output persistence | remote result handoff | remote/local return | total | residual |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| attempt_0000.json | 0.6 | 9.5 | 21,563.3 | 728.7 | 3,460.2 | 2,232.6 | 1,600.7 | 2,030.1 | 996.7 | 55.7 | 96.6 | 654.3 | 96.2 | 5,039.7 | 722.3 | 427.2 | 600.8 | - | 13.0 | 36,495.0 | -74.2 |
| attempt_0001.json | 0.8 | 6.0 | 6,805.7 | 1,160.2 | 33.1 | 826.1 | 1,184.4 | 184.9 | 971.5 | 73.7 | 95.6 | 685.0 | 86.6 | 5,004.6 | 861.6 | 380.8 | 593.8 | - | 16.5 | 16,960.4 | -185.0 |

## Per-run acceptance checks (valid cold runs)

| attempt | <13500 ms | 1 migration | worker ready | join ready | cache-only graph load | no fallback | no sampler-absent-pending | no cancelled worker | output correct | residual <=100 ms |
|---|---|---|---|---|---|---|---|---|---|---|
| attempt_0000.json | N | Y | Y | Y | Y | Y | Y | Y | Y | Y |
| attempt_0001.json | N | Y | Y | Y | Y | Y | Y | Y | Y | N |

## Pass / fail conclusion

- Valid cold runs collected: **2** / 3
- command->response distribution: min 16775.3 ms, median 36420.8 ms, max 36420.8 ms; all < 13500 ms: no
- Failures:
  - only 2/3 valid cold runs
  - command->response >= 13500 ms on 2 run(s)
  - aborted: early_stop:2_runs_over_13500ms
  - attempt_0001.json: residual -185.0 ms > 100 ms

**FAIL** — see the failures above and the stage attribution to identify the exact remaining stage.

## Files changed

- `V2_EXCLUSIVE_OWNER_TOTAL_WALL_6_RUN_REPORT.md`

Final commit SHA: `4e849e5e52489469da55f3f9dcb21949acae8e11`
