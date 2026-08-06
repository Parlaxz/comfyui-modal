# V2 Exclusive-Owner Total-Wall Validation — Six-Run Report

> Shadow deployment only. Best-case production candidate: `COMFYMODAL_V2_UNET_EXCLUSIVE_OWNER=1`, rehoming OFF, all page-path/synthetic-H2D/backing-verify/pretouch/quiesced/variance/host/full-trace diagnostics OFF, cloud=unpinned, region unpinned, single-use containers, minimal teardown.

## Protocol

- One clean shadow app deployed on `main`.
- Container env assertion (remote `run_env_probe`) before any measured run; study aborts on any gate mismatch.
- Snapshot-build request and the immediately following request excluded.
- Target: **3 valid cold single-use runs**; max 8 post-deploy attempts; 25.0 s gaps.
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
| `COMFYMODAL_V2_CLOUD` | `gcp` |
| `COMFYMODAL_V2_REGION` | `(absent/empty)` |

- min_containers=`0`, scaledown_window=`4`, single_use_containers=`True`

## Every attempt (preserved)

| attempt | class | cmd->resp (ms) | restore (ms) | join wait (ms) | worker term | join outcome | migrations | graph load wall (ms) | output |
|---|---|---:|---:|---:|---|---|---:|---:|---|
| attempt_0000.json | SKIP | 55,802.9 | 1,704.8 | - |  | - | 0 | 8,318.1 | OK |
| attempt_0001.json | SKIP | 20,947.2 | 494.1 | 641.0 | ready | ready,ready | 1 | 3.2 | OK |

## Six-run distribution (valid cold runs)

| metric | count | min | median | p90 | max |
|---|---:|---:|---:|---:|---:|
| command -> response (primary) | 0 | - | - | - | - |
| local preparation | 0 | - | - | - | - |
| modal handle and submission | 0 | - | - | - | - |
| command -> Python restore start (pre-Python Modal scheduling) | 0 | - | - | - | - |
| restore | 0 | - | - | - | - |
| restore end -> method entry | 0 | - | - | - | - |
| method entry -> UNET ownership claim (concurrent) | 0 | - | - | - | - |
| UNET claim -> ready (concurrent) | 0 | - | - | - | - |
| sampler graph-join wait | 0 | - | - | - | - |
| sampling | 0 | - | - | - | - |
| VAE | 0 | - | - | - | - |
| output persistence | 0 | - | - | - | - |
| total accounted | 0 | - | - | - | - |
| remaining residual | 0 | - | - | - | - |

## Stage attribution per valid run (ms)

| attempt | local preparation | modal handle and submission | command -> Python restore start (pre-Python Modal scheduling) | restore | restore end -> method entry | method entry -> UNET ownership claim (concurrent) | UNET claim -> ready (worker load, concurrent) | remote method setup | PromptExecutor/cache setup | first node to CLIP | CLIP to sampler node | sampler graph-join wait | sampler node to sampling | sampling | post-sampling transition | VAE | output persistence | remote result handoff | remote/local return | total | residual |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|

## Per-run acceptance checks (valid cold runs)

| attempt | <13500 ms | 1 migration | worker ready | join ready | cache-only graph load | no fallback | no sampler-absent-pending | no cancelled worker | output correct | residual <=100 ms |
|---|---|---|---|---|---|---|---|---|---|---|

## Pass / fail conclusion

- Valid cold runs collected: **0** / 3
- Failures:
  - only 0/3 valid cold runs
  - command->response >= 13500 ms on 0 run(s)
  - aborted: early_stop:2_runs_over_13500ms

**FAIL** — see the failures above and the stage attribution to identify the exact remaining stage.

## Files changed

- (none)

Final commit SHA: `910d546647458464ffbbaf7ea2c6890ecaef5ddf`
