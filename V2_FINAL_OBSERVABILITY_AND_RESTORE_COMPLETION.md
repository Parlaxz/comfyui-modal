# V2 Final Observability and Restore Completion

**Campaign date:** 2026-08-13  
**Scope:** Final frozen-VRAM restore-arm wiring and observability/waterfall validation only. No sampling, CacheDiT, Step-3, snapshot composition, model-loading policy, deployment shape, dependency set, or accepted optimization behavior was intentionally changed.  
**Final verdict:** **CURRENT V2 OPTIMIZATION / OBSERVABILITY SET NOT COMPLETE**

---

## Executive result

The frozen-VRAM restore arm is operational on request restore, the final deployment retained the required identity and architecture parity, and the single validation/discard generation completed with a correct output and Step-3 fast-path consumption. The waterfall also reconciled the host-visible command-to-response interval to a 1.065 ms residual.

The set is not complete because two explicit observability requirements remain unmet in the only permitted validation artifact:

1. The live waterfall did not consume the real active-read interval. It rendered `Checkpoint read (overlap: H2D span fallback)` as 3.550 s, effectively matching the separately measured synchronized H2D span of 3.542 s. The request's active-read record was present and measured 1.974 s, but it did not reach the rendered checkpoint-read row.
2. Scheduling remained in `ACCOUNTED` / `TOP-LEVEL ACCOUNTED` while being excluded from the `TOTAL WALL` denominator. The result was 41.443 s accounted, or 108.298% of a 38.267 s TOTAL WALL.

Deferred-persistence trace support was implemented, but the final artifact contained no `deferred_commit_start` / `deferred_commit_end` events. The row therefore remained unavailable and live deferred-persistence observability was not demonstrated.

No health classification was added or applied.

## Execution-budget disposition

The frozen protocol allowed exactly one fresh deployment/snapshot and one validation/discard generation. Both were consumed successfully:

- Deployment: one app deployment, completed in 78.895 s.
- Generation: one campaign record, role `validation_discard`, retained `false`.
- No baseline cohort, A/B arm, retry, or additional generation was run.
- No post-validation source fix was attempted. This report is documentation of the frozen result.

The governing freeze record is `V2_FINAL_OBSERVABILITY_FREEZE.md`.

## Implemented completion set

### Frozen-VRAM restore arm

- `comfymodal_runtime/restore_memory_arm.py` resolves the in-container frozen-capacity path.
- `_runtime_env` forwards `COMFYMODAL_V2_STATE_VOLUME_ROOT=/mnt/comfymodal_runtime_state`.
- Construction and request diagnostics distinguish requested arm, effective arm, frozen-file presence, fallback reason, and whether frozen capacity was used.
- The once-per-process freeze-status guard is independent from the restore-arm diagnostic guard.

Construction wrote:

```text
[restore_memory_arm] freeze stored source=nvidia-smi vram_mib=97887 gpu_name='NVIDIA RTX PRO 6000 Blackwell Server Edition'
[restore_memory_arm] freeze status=ok path=/mnt/comfymodal_runtime_state/gpu_capacity_frozen.json ... file_written=1
```

The construction container's immediate restore occurred before the newly written volume state was visible and fell back to baseline. Later restores, including the validation request, consumed the frozen value:

```text
[v2.experiment] restore_memory arm=optimized source=snapshot_frozen vram_mib=97887
[v2.restore_memory_arm] requested=optimized frozen_capacity_path=/mnt/comfymodal_runtime_state/gpu_capacity_frozen.json frozen_capacity_present=1 effective=optimized fallback=none frozen_capacity_used=1
[v2.opt.gpu_state] total_memory_ms=frozen:97887
[comfyapp] gpu_state restored vram=97887MB ... in 3.9ms
```

Evidence: `deploy_final_obs_construction.log`; `final_obs_container_full.log:4539-4553,4609-4613`.

### Waterfall and reconciliation

- Added explicit accounting roles: `top_level`, `child`, `overlap_diagnostic`, and `reconciliation`.
- Removed `Residual (unattributed)` from the numbered stage list; reconciliation is footer metadata.
- REMOTE/PARTIAL output suppresses percentages and bars when TOTAL WALL is unresolved.
- Added unresolved pre-Python classification rather than silently folding it into another stage.
- Negative child boundaries render as unavailable (`-`), not `INVALID`.
- Node details are filtered below 25 ms unless strategically retained.
- Added a concise primary table and grouped `Expanded diagnostics`.
- Host output prefers the reconciled `waterfall_local`; duplicate fallback rendering is suppressed.

The host-reconciled result reported:

```text
COMMAND->RESPONSE       41.444s
SCHEDULING               3.176s
TOTAL WALL              38.267s
GLOBAL RESIDUAL          0.001s
RESIDUAL %               0.003%
RECONCILIATION STATUS    OK
```

The exact reconciliation values were 1.065 ms residual against a 103.609 ms tolerance.

### Active-read boundaries

`comfyapp.py` now carries active-read start/end wall and monotonic timestamps. The final request emitted a complete record:

```text
active_read_id=4862d83ff2604550
wall_ms=1973.668
file_size=12309866400
```

The H2D interval remained independently measured at `to_wall_ms=3542.091` / `to_device_ms=3542.12`. However, the final waterfall still rendered the checkpoint-read row from the H2D fallback, so end-to-end consumption by the waterfall was not completed.

Evidence: `final_obs_container_full.log:4651,4659-4663,4801-4804`.

### Deferred persistence and output

- Added deferred-commit trace-event emission around deferred persistence.
- Deferred persistence remains excluded from TOTAL WALL as a child/post-yield diagnostic.
- The final request had `commit_status=skipped`, `commit_ms=0.0`, and no deferred-commit events; the waterfall row rendered `-`.
- Output encode telemetry remained available: 566.042 ms total, including 556.344 ms PNG compression.

### CPU/cgroup and log compactness

- Improved cgroup path resolution and added process-CPU fallback.
- Added compact once-per-process unavailable-cgroup output.
- Added `COMFYMODAL_V2_QUIET` and compact submission-breakdown controls.
- Final request evidence: `source=process_cpu_fallback peak_effective_cores=7.255`; the direct process sampler observed 7.345 effective cores across 242 samples.

## Deployment and parity evidence

| Item | Final evidence |
|---|---|
| Git HEAD at freeze | `e5483d5a7a5414fc9baae84d16e02c13bf270520` |
| Branch at freeze | `TESTING2` |
| Canonical custom-node generation | `4beea0bbdb2a3e74517b90a3989b9de5` |
| Baked manifest generation | `4beea0bbdb2a3e74517b90a3989b9de5` |
| Manifest/tree match | `True` |
| Deployment hash prefix | `7a9dfb40a7cb2979` |
| ComfyUI host/container identity | `f49bdb655707b979` / `f49bdb655707b979` |
| ComfyUI core match | `1` |
| Snapshot image | `im-1y7JYrXWfP85QBgGfl0G6P` |
| Validation restore session | `13b44028096747f0ae2c8dd685deeaf4` |
| Snapshot identity | `im-1y7JYrXWfP85QBgGfl0G6P|13b44028096747f0ae2c8dd685deeaf4` |
| Snapshot models | CLIP/VAE/UNET = `1/1/0` |
| Restore RSS | `11631.48 MiB` |
| Runtime shape | 12 CPU, 32768 MB, RTX-PRO-6000, TBASE/O0 |

The accepted architecture remained `snapshot_restore_only`, inherited profile, CLIP/VAE retained, UNET excluded, native fast-disk, conditioning cache, `sampling_end`, single-use/minimal teardown, unpinned cloud/region, and ComfyUI pinned to `f49bdb6`.

## Single validation/discard generation

| Item | Value |
|---|---|
| Request ID | `v2-benchmark-0-f6598f71a74a` |
| Workflow hash | `2e43d4c0ba3b82c0` |
| Run role | `validation_discard` |
| Step-3 decision | `plan_validation_fast_path` |
| Step-3 consumed | `1` |
| Workflow registry proof | 31 workflow / 31 host / 31 snapshot; zero missing or mismatched |
| Output identity | `sha256:895deda228cc96c7bcb7de2f6b262dbb2cb62615b707cfb8fc7d2ec0093c14e7` |
| Output dimensions | 1088 x 1920 |
| Output bytes | 2,874,640 |
| Artifact | `comfymodal-data/benchmarks/runs/v2_2026-08-13_04-02-15/run_001_validation_discard.json` |
| Manifest | `comfymodal-data/benchmarks/runs/v2_2026-08-13_04-02-15/campaign_manifest.json` |

All Step-3 parity axes required for the fast path were true. Sampling, sampler settings, CacheDiT attachment, and output semantics were preserved.

## Verification completed before freeze

The implementation was locally verified before the deployment freeze:

- `tests/test_v2_final_observability.py`: 29 passed.
- Waterfall suites: 59 passed.
- Attach/restoration/GPU waterfall suites: 32 passed.
- Restore A/B suites: 10 passed.
- Step-3 suites: 93 passed.
- Final restore-arm focused run: 39 passed.

The final production-equivalent evidence then confirmed:

- frozen capacity present and used on validation restore;
- generation, dependency, ComfyUI, workflow, and registry parity;
- Step-3 fast path consumed;
- correct durable PNG descriptor;
- REMOTE/PARTIAL percentage/bar suppression;
- host reconciliation status `OK` with no numbered residual stage and no `INVALID` rows;
- process-CPU fallback telemetry.

## Remaining gaps

### 1. Active-read timestamps are not consumed by the live waterfall

The timestamps exist in the request trace, but the rendered checkpoint-read stage still uses the H2D fallback. Completion requires propagating the matching active-read record into the waterfall input and selecting its start/end interval instead of H2D. This was not fixed after validation because the one-deploy/one-generation budget was exhausted.

### 2. Accounted percentage uses inconsistent scheduling semantics

Scheduling is explicitly informational and excluded from TOTAL WALL percentages/bars, but it remains in the accounted sum:

```text
TOTAL WALL       38.267s
SCHEDULING        3.176s
ACCOUNTED        41.443s = 108.298% of TOTAL WALL
```

The accounted numerator and TOTAL WALL denominator therefore describe different intervals. Completion requires either excluding scheduling from `ACCOUNTED` when TOTAL WALL excludes it or presenting a separate command-to-response accounted total without expressing it as a percentage of TOTAL WALL.

### Evidence limitation: deferred persistence

The final request did not exercise deferred persistence. Event emission exists in source, but the only production artifact contains no deferred start/end event, so the rendered deferred-persistence timing remains unavailable. No additional request may be used to close this evidence gap under the frozen protocol.

## Final disposition

The frozen-VRAM restore-arm wiring is complete and demonstrated for the validation restore. Most final observability and waterfall requirements are also implemented and verified. The active-read waterfall input and scheduling/accounted denominator semantics remain visibly incorrect in the only allowed live artifact.

**CURRENT V2 OPTIMIZATION / OBSERVABILITY SET NOT COMPLETE**

## Evidence index

- `V2_FINAL_OBSERVABILITY_FREEZE.md` — deployment freeze, scope, architecture, and constraints.
- `deploy_final_obs.log` — deployment, generation manifest, dependency, and ComfyUI identity evidence.
- `deploy_final_obs_construction.log` — snapshot construction, frozen-capacity write, and construction restore evidence.
- `run_final_obs_validation.log` — single generation, host-reconciled waterfall, and artifact path.
- `final_obs_container_full.log` — request restore, active-read, H2D, output, CPU, and REMOTE/PARTIAL evidence.
- `comfymodal-data/benchmarks/runs/v2_2026-08-13_04-02-15/run_001_validation_discard.json` — exact validation record.
- `comfymodal-data/benchmarks/runs/v2_2026-08-13_04-02-15/campaign_manifest.json` — one-generation campaign manifest.
