# V2 Transfer-Contention Isolation and Platform-Gap Reconciliation Report

Generated 2026-08-06 from controlled cold runs on the V2 shadow app
(`stable-modal-comfy-v2-shadow`, workspace Legacy Modal Token, GPU
`rtx-pro-6000`, CPU 16, memory 49152 MiB, single-use containers,
minimal teardown, TBASE/O0, UNET activation mode `late`, variance
diagnostics off by default).

## 1. Baseline and the 9.275 s platform-entry gap

Baseline request `v2-benchmark-0-412e90ad0865` (run dir
`comfymodal-data/benchmarks/runs/v2_2026-08-06_02-09-23`):

| Account | Reported (s) | Raw-timestamp source |
|---|---:|---|
| command→response | 22.211 | local submit → final result (excluding local return handoff + local prep per the earlier accounting) |
| accounted application work | 12.936 | waterfall app stages (total 30.467 − modal scheduling 9.261 − local prep 0.480 − handle 0.012 − return handoff 7.794) |
| unreconciled residual | 9.275 | **Modal scheduling before Python resumes** (see exact reconciliation below) |
| restore | 1.954 | `restore_total_ms` 1953.443 |
| sampler lane wait | 2.213 | `sampler_lane_wait_ms` 2212.895 |
| sampling | 5.248 | `sampling_duration_ms` 5248.739 |

### 1.1 Exact cross-process timestamps (all from the baseline trace)

| Event | wall unix (s) | Δ from local submission (s) |
|---|---:|---:|
| local worker start / command start | 1785982163.386 | −0.012 |
| `modal_submit_start` (local) | 1785982163.395 | 0.000 |
| `modal_submission_attempt` (local, first iteration) | 1785982163.398 | +0.003 |
| `remote_method_entry` restore (Python resumed, first line of `restore()`) | 1785982172.7376 | **+9.340** |
| `v2_bootstrap_restore_start` | 1785982172.7452 | +9.347 |
| `v2_bootstrap_restore_end` / `remote_lifecycle_end` (restore) | 1785982174.6143 | +11.216 |
| `v2_restore_return` | 1785982174.6169 | +11.219 |
| `run_plan_method_first_line` / `remote_method_entry` (method) | 1785982174.9376 | +11.540 |
| `modal_first_remote_event` (local receive) | 1785982176.0648 | +12.667 |
| `final_result_received` (local) | 1785982193.3533 | +29.958 |

### 1.2 Explicit waterfall split (reconciled, no generic residual)

| Stage | Group | ms | Source |
|---|---:|---|---|
| Local preparation | local | 480.117 | wall events |
| Modal handle and submission | local | 12.000 | wall events |
| **Modal scheduling before Python resumes** (submission → `restore()` first line) | platform | **9,261.455** (raw events: 9,339.5–9,346.8) | wall events / `_restore_timing` |
| Application restore (bootstrap 1,869 + preamble) | application | 1,954.433 | `_restore_timing` |
| Restore-to-method entry (Modal post-restore lifecycle) | platform | 323.285 | wall events |
| Remote method setup | application | 55.551 | events |
| PromptExecutor/cache setup | application | 232.978 | metadata |
| First node → CLIP | application | 5.420 | metadata |
| CLIP → sampler node | application | 736.863 | metadata |
| Sampler node → sampling (lane wait + activation tail) | application | 2,321.623 | events |
| Sampling | application | 5,247.689 | events |
| Post-sampling transition + VAE + output persistence | application | 742.499 + 489.112 + 788.862 | events |
| Remote result handoff (last remote event → local receive) | local | 7,794.020 | events |
| Remote/local return | local | 19.982 | events |
| Captured timeline gap (accounting residual) | — | 1.396 | reconciliation |
| **Total** | | **30,467.285** | accounted 30,465.889 |

**Conclusion:** the 9.275 s "unreconciled residual" is fully attributed to
**Modal scheduling before Python resumes** (submission → container resume,
9.26–9.35 s measured from raw wall timestamps; the 9.275 vs 9.261 s delta is
the accounting basis in §1, which excluded the local return handoff). No time
is placed in a generic residual; the previously "absent" intervals
(`submission_to_remote_python_resume_ms`, `restore_method_ms`,
`restore_end_to_modal_method_entry_ms`, `remote_python_resume_to_restore_start_ms`)
are now computed from the existing `_restore_timing` raw wall fields
(`canonical_execution.py` fallback tier) and from the method-phase entry event
(phase=method preferred over the stale lifecycle events carried in the
snapshot).

## 2. UNET transfer contention A/B (diagnostic-only, default off)

- **A — overlap (unchanged production path):** the early 12.31 GB CPU→GPU
  activation runs concurrently with graph/prefill; the sampler lane absorbs
  the tail.
- **B — quiesced transfer (`COMFYMODAL_V2_UNET_QUIESCED_TRANSFER=1`,
  request-scoped allowlisted flag):** the request waits for the synchronized
  transfer to complete before graph execution begins (`unet_quiesce_wait_*`
  events); during the transfer a per-thread CPU sampler samples
  `/proc/self/task/*/stat` + comm + status (Threads, Cpus/Mems allowed),
  `/proc/self/stat` (processor), and `/sys/devices/system/node/online` every
  ~100 ms. Production behavior is unchanged (flag defaults off; no code path
  alters the overlap when off).

Protocol: interleaved A,B,A,B… with 25 s cold gaps, single-use containers,
minimal teardown, variance diagnostics ON request-scoped in both arms (same
synchronized measurement), 10 valid cold runs per condition
(`restore_count==1 && request_count==1` + fresh identity), cap 15 attempts
per condition. **20/20 attempts valid cold** (no failures).
Artifacts: `comfymodal-data/benchmarks/runs/v2_2026-08-06_03-32-44/`
(`attempt_0001..0020.json`, `summary.json`, `transfer_ab_report.md`).
Image `im-ctTBI6MvjfmGob8o6wBkZU`; regions us-east-2 / us-east4 /
ap-northeast-1.

### 2.1 Every run (ms unless noted)

| cond | attempt | cmd→resp (s) | pre-Python sched (s) | restore | tfr queue | sync tfr | GB/s | graph activity | sampler wait | sampling | vae | region |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| A | 1 | 96.1 | 77.2 | 8593.4 | 107.6 | 1593.0 | 7.73 | 551.8 | 1437.3 | 3766.7 | 379.5 | us-east4 |
| A | 3 | 16.5 | 4.4 | 973.5 | 138.8 | 2245.9 | 5.48 | 817.1 | 1894.4 | 3735.5 | 461.0 | us-east-2 |
| A | 5 | 16.9 | 4.5 | 1257.6 | 146.6 | 2221.1 | 5.54 | 900.9 | 2050.1 | 3691.7 | 462.2 | us-east-2 |
| A | 7 | 16.0 | 3.1 | 1068.4 | 52.6 | 2196.3 | 5.61 | 635.9 | 2098.4 | 3730.3 | 459.0 | us-east-2 |
| A | 9 | 16.8 | 2.9 | 1247.6 | 77.3 | 3934.6 | 3.13 | 650.4 | 3828.6 | 3701.0 | 458.8 | us-east-2 |
| A | 11 | 16.3 | 6.6 | 442.8 | 56.1 | 898.2 | 13.71 | 464.0 | 812.7 | 3655.2 | 371.3 | us-east4 |
| A | 13 | 15.9 | 3.7 | 1132.5 | 53.5 | 2205.7 | 5.58 | 855.1 | 2003.6 | 3704.4 | 477.0 | us-east-2 |
| A | 15 | 28.8 | 5.8 | 4763.1 | 1055.9 | **12780.5** | **0.96** | 2248.5 | 0.3 | 3666.1 | 368.7 | us-east4 |
| A | 17 | 29.5 | 14.6 | 4162.2 | 325.0 | 1808.1 | 6.81 | 791.5 | 1618.7 | 3750.6 | 387.5 | us-east4 |
| A | 19 | 17.5 | 4.5 | 1573.9 | 75.7 | 2126.3 | 5.79 | 692.0 | 2015.5 | 3702.2 | 462.9 | ap-northeast-1 |
| B | 2 | 16.5 | 2.8 | 884.4 | 46.3 | 3907.1 | 3.15 | 368.2 | 0.3 | 3717.5 | 471.1 | us-east-2 |
| B | 4 | 28.1 | 2.2 | 2168.3 | 15.1 | **14929.6** | **0.82** | 257.8 | 0.1 | 3716.3 | 443.8 | us-east4 |
| B | 6 | 25.1 | 5.5 | 4096.6 | 206.1 | 2381.3 | 5.17 | 244.8 | 0.1 | 3664.4 | 370.9 | us-east4 |
| B | 8 | 18.0 | 3.7 | 1680.5 | 23.7 | 2665.8 | 4.62 | 337.3 | 0.3 | 3703.7 | 480.3 | us-east-2 |
| B | 10 | 15.5 | 3.2 | 1077.5 | 48.1 | 1986.8 | 6.20 | 362.3 | 0.1 | 3726.3 | 465.7 | us-east-2 |
| B | 12 | 17.9 | 5.5 | 2723.6 | 27.6 | 986.6 | 12.48 | 249.5 | 0.1 | 3719.3 | 373.8 | us-east4 |
| B | 14 | 64.2 | 27.7 | 8557.1 | 21.4 | **17830.2** | **0.69** | 380.5 | 1.2 | 3742.4 | 472.7 | ap-northeast-1 |
| B | 16 | 20.3 | 7.1 | 1735.2 | 222.3 | 1157.2 | 10.64 | 241.7 | 0.1 | 3677.9 | 385.6 | us-east4 |
| B | 18 | 18.4 | 5.0 | 1248.4 | 17.6 | 1952.4 | 6.30 | 378.6 | 0.6 | 3713.8 | 470.7 | ap-northeast-1 |
| B | 20 | 29.9 | 18.2 | 463.8 | 15.1 | 1586.3 | 7.76 | 293.9 | 0.1 | 3759.7 | 425.8 | us-east4 |

Synchronized transfer distribution (12,309,817,472 B, CUDA-synced):

| Condition | median | min | max | slow ≥5 s | fast <5 s |
|---|---:|---:|---:|---:|---|
| A (overlap) | 2,201 ms | 898 ms | 12,781 ms | 1/10 (12.8 s @ 0.96 GB/s) | 9/10 |
| B (quiesced) | 2,184 ms | 987 ms | 17,830 ms | 2/10 (14.9 / 17.8 s @ 0.82 / 0.69 GB/s) | 8/10 |

Quiescing works as designed (B sampler wait collapses to 0.1–1.2 ms vs A's
812–3,829 ms; graph activity drops from 464–2,249 ms to 242–381 ms) **but does
not change the transfer distribution**: the slow side appears in BOTH arms
(A 1/10, B 2/10) with the same 0.7–1.0 GB/s signature, and the fast/mid side
is statistically identical (A median 2,201 vs B 2,184 ms).

### 2.2 Fast-vs-slow per-thread CPU ownership (B arm, ~100 ms sampling)

| run | sync tfr | GB/s | dominant thread CPU | 2nd thread | other 60+ threads | samples |
|---|---:|---:|---:|---:|---:|---:|
| B-12 | 987 ms | 12.5 | `python` tid80 **810 ms (82 %)** | 20 ms | ~0 | 9 |
| B-16 | 1,157 ms | 10.6 | tid80 **920 ms (80 %)** | 60 ms | ~0 | 10 |
| B-2 | 3,907 ms | 3.2 | tid80 **3,670 ms (94 %)** | 320 ms | ~0 | 36 |
| B-8 | 2,666 ms | 4.6 | tid80 **2,430 ms (91 %)** | 200 ms | ~0 | 25 |
| B-4 | 14,930 ms | 0.82 | tid80 **13,470 ms (90 %)** | 670 ms | ~0 | 136 |
| B-14 | 17,830 ms | 0.69 | tid80 **16,810 ms (94 %)** | 880 ms | ~0 | 170 |

Per-interval samples on the slow runs show process CPU delta ≈ 100–120 ms per
100 ms interval attributed ≥95 % to the single transfer thread (`python`
tid80, the coordinator-pool early-activation worker). The second thread's CPU
scales with sample count (≈5 % of wall, i.e. the sampler thread's procfs
reads) — measurement overhead, not a competitor. `cuda-EvtHandlr` is
negligible (10–230 ms). Affinity/NUMA fields were not exposed by the
container's `/proc/self/status` (`Cpus_allowed_list`/`Mems_allowed_list`
absent; fallback `/proc/self` readers added); the transfer thread's own
`/proc/self/task/<tid>/stat` field 39 was consistently **CPU 0** in both fast
and slow runs (`cpus_seen=[0]`).

**The same thread on the same CPU, with the same single-threaded CPU-mediated
copy signature (82–94 % of wall), achieves 0.7–13.7 GB/s across otherwise
identical quiesced runs — with no in-process CPU competitor present.**

## 3. Supported root cause and decision

1. **Platform-entry gap (9.275 s):** Modal scheduling before Python resumes —
   fully reconciled from raw timestamps (§1.2). Not application latency, not
   UNET transfer, not restore.
2. **Transfer bimodality:** the 12.31 GB CPU→GPU copy is single-thread
   CPU-mediated (thread CPU ≈ wall on every run, fast and slow). Quiescing the
   transfer away from graph/prefill does **not** make it consistently fast —
   the slow side (0.7–1.0 GB/s, 12.8–17.8 s) persists in arm B with zero
   in-process competition. The throughput a single thread achieves for the
   same copy on the same CPU varies 8–18× between otherwise identical runs,
   across hosts and regions. **This is host/NUMA/PCIe-side variance (host
   memory-bandwidth contention / page-to-GPU placement), not in-process
   contention.**

Per the protocol: **no application transfer change is shipped.** The quiesced
serialization remains request-scoped diagnostic-only and default-off
(`COMFYMODAL_V2_UNET_QUIESCED_TRANSFER`, allowlisted, never set in
production). Commit bisection, pinning, pretouch, activation-mode and
teardown comparisons were not revisited. No speculative fix was implemented.

## 4. Verification evidence

- 20/20 interleaved attempts cold-valid (10 A + 10 B), every attempt
  preserved; 25 s gaps; single-use; minimal teardown; both arms measured with
  the identical CUDA-synced synchronized-load instrumentation.
- Per-run waterfall reconciliation residual ≤ 1.4 ms on the baseline run.
- Unit tests: new `tests/test_v2_quiesced_transfer.py` (15 tests: env gate
  default-off, wait helper no-op/bounded/events, allowlist, proc-stat parser,
  sampler summary, variance-record carry) — all pass. Existing suites
  (`test_v2_variance_worker`, `test_v2_variance_cold`, `test_v2_waterfall`,
  `test_v2_teardown_diagnostics`, `test_v2_unet_early_activation`,
  `test_v2_variance_matrix`, `test_request_variance_env`,
  `test_reconciliation_intervals`, `test_v2_local_submission_timing`,
  `test_request_origin_summary`) pass. `test_v2_observability_instrumentation`
  unchanged at its pre-existing 22 failures on HEAD (one pre-existing AST
  failure `test_resume_before_configure_runtime` is fixed by the true
  first-line resume capture).
- Deploy-config note: the shadow deployment required
  `COMFYMODAL_V2_VAE_SNAPSHOT=1` to match the request VAE identity
  (diagnosed via the new exact mismatch-field reporting; the earlier shadow
  deployment had it enabled). This is a deploy-env correction, not a code
  regression.

## 6. Region-pinned comparison (us-east-2 vs us-east4)

Follow-up controlled test (10 valid cold runs per region, single-use, minimal
teardown, production overlap arm, diagnostics ON, 25 s gaps; first 2 attempts
per block excluded as snapshot builders). Deployments pinned via
`COMFYMODAL_V2_REGION` (Modal 1.4.3 `region=` kwarg). Artifacts:
`comfymodal-data/benchmarks/runs/v2_2026-08-06_05-39-25` (us-east-2) and
`v2_2026-08-06_05-56-29` (us-east4). Every run verified on the pinned region.

| Metric | us-east-2 (AWS) | us-east4 (GCP) |
|---|---:|---:|
| Transfer median / range | **2,165 ms** / 2,088–2,355 ms (tight, ±6 %) | **983 ms** / 925–5,785 ms (wide) |
| GB/s median / range | 5.69 / 5.23–5.90 | 12.53 / 2.13–13.31 |
| Bad runs (>5 s) | **0/10** | 1/10 (5,785 ms @ 2.13 GB/s) |
| cmd→response median / avg | 24.7 s / 34.7 s (4 runs 31–94 s scheduling) | **18.0 s / 17.7 s** (tight 15.3–19.3 s) |
| Restore median | 1.17 s | 0.83 s |
| Sampler lane wait median | 1,828 ms | 880 ms |
| Sampling median | 3,701 ms | 3,703 ms |

Reading: the two pools differ in KIND, not just quality. The AWS us-east-2
pool is the consistency play — zero slow transfers in 18 controlled runs
(and tight ~2.2 s @ 5.7 GB/s every time) — but it is never fast and its
Modal scheduling is per-session erratic (4/10 runs this session at 31–94 s).
The GCP us-east4 pool is typically **2× faster** (0.98 s @ 12.5 GB/s, tight
end-to-end ~18 s) but carries the slow tail: 3/19 controlled runs >5 s this
session and last (12.8 s / 14.9 s / 5.8 s). Historically every slow draw
cluster lives on GCP us-east4 (9/35) with occasional us-east-2 (2/15) and
ap-northeast-1 (1/3).

Conclusion: neither region is strictly better. If the goal is worst-case
elimination, pin us-east-2; if typical latency matters more than the tail,
us-east4 wins end-to-end. This is consistent with the host-side conclusion —
the bimodal slow side is a property of specific host pools, and pinning
changes the odds but cannot eliminate the mechanism.

## 7. Files changed

- `comfymodal_runtime/modal_app.py` — region pinning via
  `COMFYMODAL_V2_REGION` (allowlisted; `region=` kwarg on the Modal cls;
  default off; non-allowlisted value fails at deploy time).

- `comfymodal_runtime/thread_cpu_sampler.py` — new: per-thread CPU delta
  sampler (proc stat/comm/status, affinity, NUMA, processor; bounded).
- `comfymodal_runtime/model_preload.py` — `quiesced_transfer_enabled()`,
  `wait_unet_activation_quiesced()` (bounded, emits
  `unet_quiesce_wait_start/end`), sampler integration around the synchronized
  load, `unet_quiesced_transfer` event + worker-variance carry, identity meta.
- `comfymodal_runtime/modal_app.py` — allowlist entry
  `unet_quiesced_transfer`; quiesce wait before `execute_async`
  (`unet_quiesce_request` event); `remote_python_resume` captured at the true
  first line of `restore()`; exact mismatch-field reporting for
  `cpu_snapshot_models_request_bound` (request/snapshot key hashes + unet/clip/
  vae mismatch fields).
- `comfymodal_runtime/v2_waterfall.py` — detail stages: UNET quiesce wait,
  transfer queue delay, synchronized transfer, graph/prefill activity.
- `tools/benchmark_v2_direct.py` — `_timing` platform-entry intervals
  (submission→resume, resume→restore-start, restore→method-entry,
  method-entry→first-event, first-event→final) + transfer stages + quiesced
  record; `--quiesced-transfer`; `--transfer-ab` interleaved mode with
  `transfer_ab_report.md`; origin keys; `--region-ab` pinned-region mode
  (skip-first-2 snapshot builders, collect N valid cold, `region_ab_report.md`).
- `tools/variance_report.py` — `extract_run_metrics` surfaces the new
  platform-gap + transfer + per-thread ownership fields.
- `canonical_execution.py` — `_restore_timing` fallback tier (raw wall fields
  already present in every result), method-phase entry-event preference.
- `deploy_v2_transfer_ab.bat`, `run_transfer_ab.bat`,
  `deploy_and_run_region_ab.py` — reproduction wrappers (verified production
  config incl. `COMFYMODAL_V2_VAE_SNAPSHOT=1`; region pinning via env).
- `tests/test_v2_quiesced_transfer.py` — new tests.
- `V2_TRANSFER_AND_PLATFORM_GAP_REPORT.md` — this report.

Final commit SHA: see commit message.

## Replication note

Reproduce the region-pinned comparison (one region per invocation):

```
:: Block 1 — us-east-2 (AWS)
python deploy_and_run_region_ab.py us-east-2

:: Block 2 — us-east4 (GCP)
python deploy_and_run_region_ab.py us-east4
```

Each invocation: (1) deploys `stable-modal-comfy-v2-shadow` with the verified
production config (CPU 16 / mem 49152 MiB, TBASE/O0, single-use containers,
minimal teardown, VAE snapshot, exact CLIP conditioning cache, mode `late`,
diagnostics off by default) plus `COMFYMODAL_V2_REGION=<region>` which pins
the deployment via Modal's `region=` kwarg; (2) runs
`tools/benchmark_v2_direct.py --region-ab <region> --teardown minimal`, which
skips the first 2 attempts (snapshot/cache build + the run after — both
excluded unconditionally even if the second looks clean), then collects 10
valid cold runs (restore_count==1 && request_count==1 && fresh identity) with
25 s gaps, cap 15 attempts. Every attempt is preserved as
`attempt_<seq>.json` in a fresh
`comfymodal-data/benchmarks/runs/v2_<utc-timestamp>/` dir plus
`region_ab_report.md` and `summary.json`. The A/B transfer and quiesced modes
use the same wrappers (`run_transfer_ab.bat` for the interleaved 10+10 A/B,
`--quiesced-transfer 1` + `--variance-cold` for a single quiesced block).

Key numbers to compare after each block (from `region_ab_report.md` or the
attempt files): synchronized transfer wall/GB/s
(`unet_activation_worker_variance.synchronized_load`), command→response,
pre-Python scheduling, restore, sampler lane wait. The first block's first run
is always a cache-miss/snapshot build; the second block reuses the warm
conditioning-cache volume, so its first run is often an `exact_hit` — the
skip-first-2 rule keeps both blocks comparable regardless.
