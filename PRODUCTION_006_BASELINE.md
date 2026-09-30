# PRODUCTION-006 BASELINE

Immutable production anchor for the Golden Parallel C0 source loader.
Created only after a clean, committed, redeployed baseline reproduced the
hardware-verified stabilization on a frozen 10-run true-cold H100 cohort.

## Identity

| field | value |
|---|---|
| tag | `production-006` (annotated) |
| commit | `5d41f742f42eb2fbddc3bbfa5641fe01dd35faa6` + this documentation commit |
| tree | `ade772218bd557db2a9912d824fc13f6d0605a97` (runtime tree, unchanged by this doc) |
| parent | `7bc05e1a5c1b6f61c1d54bbd9da2bce422d0bc21` |
| branch | `promotion/production-006` |
| worktree | `.slim/worktrees/production-006` |
| destination | Testing 9, `ws_ee7221847f7d` |

The documentation commit changes no runtime module. Every module probed by
`v2ctl source-probe` is byte-identical to the cohort-tested commit
`5d41f742f42eb2fbddc3bbfa5641fe01dd35faa6`.

## Root cause fixed

Three defects, all in the C0 source-owner subsystem. No architecture change, no
loader parameter change.

1. **Fresh vs Whole runtime lifecycle mismatch.** The counted H100 profile
   pinned `COMFYMODAL_GOLDEN_C0_MMAP_LIFECYCLE = "fresh"`, so every 64 MiB
   source extent was mapped and unmapped per operation and re-faulted from the
   volume. Proven by a controlled single-variable contrast on the same profile,
   worker kind, concurrency, operation counts and output SHA: `whole` measured
   6.4/6.2 GB/s while `fresh` measured 0.145-1.597 GB/s, with `valid=true` and
   `fallback=0` in both cases. Fixed by pinning `whole`.

2. **Pre-ack READY_BLOCK generation race.** `plan_once` assigned
   `_planned_generation` *after* the PLAN-ack drain, so a READY_BLOCK that beat
   `PLAN_ACK` was resolved against the previous generation and orphaned its
   slot. The whole-file mapping made small checkpoints read faster than the ack,
   which turned a latent race into a frequent one (VAE load 35.06 s). Fixed by
   publishing the generation before any block can be read.

3. **Drop-path starvation.** Ownership recovery only ran when no doorbell
   arrived at all, and never before the deadline return, so a dropped or
   coalesced announcement left a slot permanently READY. The consumer then waited
   for a doorbell that could not exist. Fixed by re-deriving READY ownership
   from the shared control block on the drop path and before the deadline
   return.

## Safety bounds

| bound | value | scope |
|---|---|---|
| CLIP model-load gate | 30 s | `publish_all`, role-tagged `golden_clip_load_timeout_30s` |
| UNET model-load gate | 30 s | `publish_all`, role-tagged `golden_unet_load_timeout_30s` |
| Total Golden request gate | 40 s | scoped to Golden work; cancelled once telemetry is durable |
| Post-request exit bound | 15 s | armed only after telemetry persisted |

The former 120 s `publish_all` default is **retired**; it was the source of the
observed two-minute requests. The 40 s request gate fires from a watchdog
thread and dumps every thread stack, which is what makes any future stall
self-diagnosing.

Gates fail closed: terminal diagnostic, invalid/DNF, no continuation into later
stages, bounded cleanup of this request's own source/H2D state.

## Exact invocation

Run from the promotion worktree, one request per invocation:

```text
python -m tools.v2_control.cli --profile golden_p1_parallel_c0_source_h100 golden deploy --app batch-c0-source-h100
python -m tools.v2_control.cli --profile golden_p1_parallel_c0_source_h100 golden publish-custom-nodes
python -m tools.v2_control.cli --profile golden_p1_parallel_c0_source_h100 source-probe --app batch-c0-source-h100
python -m tools.v2_control.cli --profile golden_p1_parallel_c0_source_h100 golden run --app batch-c0-source-h100
```

## Profile and resolved config

| field | value |
|---|---|
| profile | `golden_p1_parallel_c0_source_h100` |
| app / class / method | `batch-c0-source-h100` / `ModalRuntimeEntrypointV2` / `run_golden_parallel_stream` |
| GPU / CPU / memory | `H100!` / 12 / 24576 MiB |
| expected SHA | `3a6a03064c7e6e01ede339ada63daaea4cbf793f387f4faadbb101a787024577` |
| source lifecycle | `whole` |
| source workers | 4 threads, one CUDA-sterile source owner |
| QD | QD4 |
| geometry | 8 x 64 MiB slots, 512 MiB arena |
| pacing | 4 ms global source-start spacing |
| H2D | C0 async dispatcher, one_shot completion events |
| profile config fingerprint | `adaf22ade8ac9447458671dbc5c74deb8013f457968d384f48ab4caafd10ed40` |

## Deployment identity

| field | value |
|---|---|
| deployment fingerprint | `1b0e49ead74200733c5e91dc2f0d662c8c8361299204807f225d9f3ec54a71d3` |
| source probe | PASS / MATCH, 16/16 modules |
| `golden_source_threads.py` | `42daa9acb0529e688d6687bd...` |
| prior dirty verified deploy | `a1add583ca7deb02735a14f8cc5b842182bbdf9a981d2ef9231fe3efa84d6e46` |

## Dirty-deployment provenance

`a1add583` was the hardware-verified treatment, produced from `TESTING8` at
`7bc05e1a` with `dirty: true` (34 paths, stabilization uncommitted). It could
not be tagged, because tagging that commit would not tag the fix.

The clean promotion worktree was reconstructed from it and proven equivalent:
**all 16 source-probed runtime modules are byte-identical** to what `a1add583`
actually ran.

Intentionally excluded from the promotion commit, all verified not exercised by
this path: `__init__.py` studio `remote_inventory` lazy imports (inside
`if _server:` download routes) and the `studio_*`, `web/*`,
`dependency_resolver.py`, `model_library_routes.py`, `remote_inventory.py`,
`workflow_metadata.py` operator work. Excluding these together with the modules
they import keeps the tree self-consistent.

Required and included beyond the three stabilization source files:
`config/v2/flag_registry.toml` (declares `C0_SOURCE_WORKER_KIND` used by the
profile), the counted profile itself, and `latest_benchmark_workflow.json`
(gitignored upstream, force-added here because it defines the expected SHA and
is therefore required to reproduce it).

## Tests

Focused: 62 passed, 5 skipped (`test_golden_parallel_foundation.py`,
`test_c0_source_threads.py`). Behavioral coverage includes whole-lifecycle
selection, pre-ack READY_BLOCK behavior, table recovery, drop-path recovery,
deadline recovery, the 30 s CLIP and UNET gates, genuinely blocking gate
enforcement (a blocking wait is capped, not merely observed), no continuation
after a gate, cleanup/quiescence after timeout, slot-ownership token safety, and
unchanged normal-path behavior.

Unrelated pre-existing failures in `test_rx9p_h_identity_chain.py` (2) are
acknowledged and unchanged from the clean base; the modules involved
(`tools/v2_control/experiment_evidence`) are untouched by this work. Not fixed
here by design.

## Clean 10-run cohort

Frozen commit `5d41f742`, deployment `1b0e49ea`, Testing 9, no code or config
changes during the cohort. No valid run was discarded.

| # | cohort | valid | SHA | wall ms | CLIP | UNET | VAE | source GB/s |
|---|---|---|---|---|---|---|---|---|
| 1 | 06-57-09_540102 | yes | 3a6a0306 | 15101 | 3958 | 5810 | 645 | 2.27 / 2.64 |
| 2 | 06-58-19_6268f6 | yes | 3a6a0306 | 14744 | 5292 | 4100 | 856 | 1.64 / 3.30 |
| 3 | 06-58-54_769062 | yes | 3a6a0306 | 10084 | 1779 | 3107 | 605 | 4.74 / 4.36 |
| 4 | 06-59-14_d455cc | yes | 3a6a0306 | 9872 | 1747 | 3044 | 537 | 4.84 / 4.60 |
| 5 | 06-59-39_717795 | yes | 3a6a0306 | 10054 | 1936 | 3080 | 618 | 4.59 / 4.13 |
| 6 | 07-00-05_c17ce1 | yes | 3a6a0306 | 10213 | 1870 | 2883 | 498 | 4.51 / 4.62 |
| 7 | 07-00-29_3c0f45 | yes | 3a6a0306 | 12800 | 2504 | 4379 | 1054 | 3.41 / 2.89 |
| 8 | 07-01-55_b4b60b | yes | 3a6a0306 | 9240 | 1906 | 2609 | 401 | 4.64 / 4.82 |
| 9 | 07-02-53_0f0947 | yes | 3a6a0306 | 13730 | 2490 | 6331 | 630 | 3.35 / 1.96 |
| 10 | 07-03-17_58d9bc | yes | 3a6a0306 | 9587 | 1764 | 2745 | 576 | 5.14 / 5.19 |

All 10: `restore_count=1`, `request_count=1`, `single_use_containers=true`,
`mmap_lifecycle=whole` observed in runtime child evidence.

## Aggregate statistics

| metric | median | mean | SD | CV | min | p90 | max |
|---|---|---|---|---|---|---|---|
| CLIP load (ms) | 1888 | 2000 | 294 | 14.7% | 1747 | 2490 | 2504 |
| UNET load (ms) | 3062 | 3522 | 1176 | 33.4% | 2609 | 4379 | 6331 |
| VAE load (ms) | 590 | 615 | 180 | 29.3% | 401 | 630 | 1054 |
| Golden wall (ms) | 10069 | 10698 | 1528 | 14.3% | 9240 | 12800 | 13730 |

Source throughput: median 4.594 GB/s, mean 4.237 GB/s, worst 1.963 GB/s.

Reference envelope from the hardware-verified dirty cohort, for comparison:
CLIP median 1826 / max 2339 ms, UNET median 2740 / max 3248 ms, wall median
9839 / max 10672 ms, source median 4.654 / worst 3.565 GB/s. This cohort is
slightly slower and wider-spread at the UNET end (CV 33.4%); no model load
approached tens of seconds and no run fell into the catastrophic 0.1-1 GB/s
band.

## Tail proof

- CLIP 30 s model-load gate failures: **0**
- UNET 30 s model-load gate failures: **0**
- Outer timeouts: **0**
- Runs exceeding 14 s Golden wall: 2 of 10 (14744 ms, 15101 ms)
- Catastrophic source collapse (0.1-1 GB/s): **0**; worst observed 1.963 GB/s
- Model loads in the tens of seconds: **none**; max CLIP 2504 ms, max UNET 6331 ms

## Output proof

Exact output SHA `3a6a03064c7e6e01ede339ada63daaea4cbf793f387f4faadbb101a787024577`
on **10 of 10** runs. Fallback count 0 on all runs.

Note: the streamed log emits
`WARNING output_sha_mismatch expected=790c3052... observed=3a6a0306...`. That
is the hardcoded module constant `golden_serial.EXPECTED_OUTPUT_PNG_SHA256`,
compared against this parallel path's real output. The runtime documents it as
warning-only and authoritative-observed-hash; it is not a failure and not
indicative of this baseline.

## Runtime truth

`child_ready_evidence.mmap_lifecycle == "whole"` on 10 of 10 runs, read from
the source owner's own child telemetry inside the container. Profile and
provenance values were **not** accepted as proof, because an earlier deployment
incident proved configuration can describe intent while a previously deployed
image actually runs something else.

## Diagnostic instrumentation

The counted profile runs with `COMFYMODAL_GOLDEN_STAGE_DIAGNOSTICS = "0"`, so a
prior stall printed nothing between restore and completion. Two always-on,
passive observability additions are therefore part of this baseline:

- `[v2.golden.progress]` stage begin/end heartbeats, toggleable via
  `COMFYMODAL_GOLDEN_PROGRESS_HEARTBEAT` (default on). The request wall gate
  prints the last stage reached and every thread stack when it fires.
- `[v2.golden.outer]` outer-method lifetime marks around the streaming yield
  seam (`remote_method_entry`, `pre_yield`, `post_yield_resume`,
  `remote_method_return`, plus `OUTER_SUMMARY`).

These add one monotonic read and one print per boundary and do not alter any
performance mechanic.
