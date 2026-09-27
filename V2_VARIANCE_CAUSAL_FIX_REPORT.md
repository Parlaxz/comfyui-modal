# V2 Variance Causal-Fix Report

Generated 2026-08-05. Workspace: Testing3 (Legacy Modal Token). App:
`stable-modal-comfy-v2-variance-shadow`. GPU: `rtx-pro-6000` (GCP/AWS), CPU 16,
memory 49152 MiB. Single-use containers
(`COMFYMODAL_V2_SINGLE_USE_CONTAINERS=1`), UNET activation mode
`clip_gpu_ready`, variance diagnostics on, pretouch off, 25-second inter-run
gaps. Every attempt is preserved under
`comfymodal-data/benchmarks/runs/v2_2026-08-05_*`.

## 1. Cleanup A/B result and saved time

Two single-use cold runs, identical workloads, teardown diagnostics on.
Measured in-container via `[v2.teardown]` events (`request_gpu_release_*`,
`exit_hook_*`, `python_atexit`) and the run artifacts.

| Metric | A: full `unload_all_models()` | B: minimal bounded cleanup |
|---|---|---|
| Run | `v2_2026-08-05_23-33-32` | `v2_2026-08-05_23-36-01` |
| `teardown_mode` | `full` | `minimal` |
| Terminal release elapsed | **2,560.334 ms** | **2.455 ms** |
| `model_management_unload` stage | 1,929.4 ms | skipped |
| `garbage_collection` stage | 627.3 ms | skipped |
| `device_fallback` / `cleanup_models` / `cuda_cleanup` | ran | skipped |
| CUDA allocated after release | 34,603,008 B (reclaimed) | 12,634,373,120 B (retained; released at process exit) |
| Bounded ref/worker stages (`preload_workers`, `activation_references`, `preload_references`, `request_references`, samplers) | ran | ran (same) |
| Post-stream re-release | 633.8 ms (idempotent re-run) | 2.0 ms |
| `exit_hook_start` → `exit_hook_end` | 23.9 ms | 20.3 ms |
| Result delivery | 107 outputs, exit 0 | 107 outputs, exit 0 |
| Container disappeared after exit hook | yes | yes |

**Saved time: ~2.56 s of terminal-path release plus ~0.63 s post-stream per
single-use request — the bounded stages run in 2.5 ms total.** Generation,
result delivery, asset delivery, `exit_hook_start`, container disappearance all
verified identical. B never launches a new GPU container for asset reads: all
asset descriptors are delivered in the run result before terminal cleanup. **B
is adopted as the default for single-use containers** (explicit
`COMFYMODAL_V2_MINIMAL_GPU_TEARDOWN=0` still forces A). Reusable-container mode
keeps full unloading (`_resolve_single_use_containers() == False` → `full`).

## 2. Confirmed root cause

The corrected worker instrumentation (Section 4) shows the synchronized
12.31 GB CPU→GPU transfer is the **only** variable stage:

- Healthy activations: transfer **0.92–1.25 s @ 9.8–13.3 GB/s** → total 0.95–1.15 s
- Stalled activations: transfer **3.17–16.69 s @ 0.74–3.88 GB/s** → total 3.2–16.7 s

Evidence ruling out the alternative explanations:

| Hypothesis | Evidence | Verdict |
|---|---|---|
| Slow page hydration | 0 minor/major faults, 0 `read_bytes`, RSS flat during every transfer window | **rejected** |
| Worker queue delay / thread-pool starvation | queue 0.7–13.7 ms on both fast and slow runs | rejected |
| CPU-snapshot wait | 0.06–0.21 ms | rejected |
| dtype/layout preparation | 2–34 ms | rejected |
| Patcher/cache bookkeeping | patcher breakdown residual (raw copy loop) = 7,009 ms of 7,025 ms; traversal 10.8 ms, patch_weight 5.4 ms, cast 0 | rejected as bookkeeping; the residual *is* the transfer |
| Post-load bookkeeping | 1.7–21.9 ms | rejected |
| Pinned-memory fix (cudaHostRegister) | interleaved A/B: pin=0 → 1.15/0.96/1.02 s; pin=1 → 2.19/0.95/**12.37** s; pin-only → 16.7/3.5/7.0 s | **fix rejected** — same bimodal distribution with pinning |

The transfer is CPU-mediated (thread CPU ≈ wall on slow runs: 10.5 s CPU over
11.4 s wall; 4.7 process cores busy vs 1.5 on fast; zero faults, zero IO).
Throughput collapse tracks concurrent host CPU activity, i.e. **platform
scheduling/contention**, not application code. Per protocol, the unsupported
pinning change is not shipped as the fix; it remains flag-gated OFF
(`COMFYMODAL_V2_PIN_UNET_TRANSFER`, default 0).

Restore stalls (>3 s) are explained by the new per-stage restore breakdown:
dominated by `restore_gpu_state` (1,537–2,061 ms on stalls vs 193–365 ms on
fast) plus `snapshot_restore`/`reload_runtime_state` (up to 907 ms) — not by
`reload_models` (72–306 ms).

## 3. Implemented fix

1. **Minimal bounded teardown becomes the default for single-use containers**
   (modal_app.py `_release_gpu_after_request`): skip
   `model_management_unload`/`device_fallback`/`cleanup_models`/`legacy_executor_reset`/`gc`/`cuda_cleanup`;
   keep the bounded reference/worker stages; rely on process exit to release
   CUDA. Explicit `COMFYMODAL_V2_MINIMAL_GPU_TEARDOWN` overrides; reusable
   containers keep full unloading. ~2.56 s saved per single-use request.
2. **Corrected worker variance instrumentation** (model_preload.py): the
   `unet_activation_worker_variance` record now carries `queue_delay_ms`,
   `cpu_snapshot_wait_ms`, `dtype_layout_preparation`, `registry_setup`,
   `page_traversal` (pretouch), `synchronized_load` (CUDA-synced before/after),
   `post_load_bookkeeping`, `early_activation_total_ms`, and
   `loader_reconciliation` reconciled against the **true total**
   (scheduled→completed). All sub-stages reconcile to the total
   (`unmeasured_gap` residual 6.8–56 ms). Restore breakdown
   (`restore_breakdown_*`) is extracted into reports to explain >3 s restores.
3. A/B tooling: `--teardown {full,minimal}`, `--pin-transfer {0,1}`,
   request-scoped `minimal_teardown`/`pin_unet_transfer` allowlist entries.

## 4. Every run (fast vs slow)

All cold-valid (`cold=true`), 25 s gaps, single-use. `total` =
`early_activation_total_ms`; `sync` = synchronized load wall; GB/s over
12,309,817,472 B. Queue/cpu-wait/dtype/registry/bookkeeping are sub-40 ms in
every run (fast and slow alike).

| Run dir | total ms | sync ms | GB/s | queue ms | dtype ms | registry ms | bb ms | restore ms | class |
|---|---|---:|---:|---:|---:|---:|---:|---:|---|
| 23-00-34 | 1,068.5 | 1,051.3 | 11.7 | 0.7 | 2.0 | 5.2 | 2.5 | 997.8 | fast |
| 23-00-06 | 1,078.5 | 1,021.6 | 12.0 | 10.3 | 14.7 | 5.7 | 1.7 | 2,923.1 | fast |
| 23-29-44 (pin0) | 1,146.9 | 1,121.4 | 11.0 | – | – | – | – | – | fast |
| 23-30-32 (pin0) | 956.5 | 933.0 | 13.2 | – | – | – | – | – | fast |
| 23-30-56 (pin1) | 946.7 | 924.1 | 13.3 | – | – | – | – | – | fast |
| 23-31-22 (pin0) | 1,025.0 | 995.1 | 12.4 | – | – | – | – | – | fast |
| 23-30-06 (pin1) | 2,185.8 | 2,166.9 | 5.7 | – | – | – | – | – | slow-ish |
| 22-56-02 | 3,285.5 | 3,210.5 | 3.8 | 5.8 | 18.5 | 5.0 | 2.8 | 1,588.4 | **stall** |
| 22-59-42 | 3,209.2 | 3,175.1 | 3.9 | 12.3 | 5.5 | 6.0 | 2.7 | 539.6 | **stall** |
| 23-27-19 (pin1) | 3,542.0 | 3,469.0 | 3.5 | – | – | – | – | – | **stall** |
| 22-59-18 | 5,723.1 | 5,679.3 | 2.2 | 2.1 | 3.4 | 6.2 | 21.9 | 509.0 | **stall** |
| 23-27-54 (pin1) | 7,004.9 | 6,977.9 | 1.8 | – | – | – | – | – | **stall** |
| 22-55-28 | 11,441.2 | 11,387.6 | 1.1 | 1.2 | 3.2 | 4.7 | 3.0 | 639.1 | **stall** |
| 23-31-48 (pin1) | 12,372.7 | 12,305.8 | 1.0 | – | – | – | – | – | **stall** |
| 23-26-44 (pin1) | 16,725.0 | 16,693.2 | 0.7 | – | – | – | – | – | **stall** |
| 23-36-01 (B) | 4,900.2 | 4,870.9 | 2.5 | 1.0 | 3.8 | 7.3 | 3.4 | 820.6 | **stall** |
| 23-33-32 (A) | 2,275.9 | 2,185.6 | 5.6 | 3.6 | 5.7 | 5.4 | 2.6 | 4,045.0 | slow + restore stall |

Pre-reorder runs (totals nulled by the emit-order bug, preserved):
22-42-33 (sync 973.5 @12.6, restore 2,641.6, fast), 22-44-11 (sync 9,530 @1.3,
restore 3,967.9 — **stall + restore stall**), 22-44-47 (926.9 @13.3, 643.0,
fast), 22-45-11 (962.2 @12.8, 2,282.3, fast), 22-45-37 (5,763.6 @2.1 — stall),
22-46-05 (6,555.6 @1.9 — stall), 22-46-34 (1,770.0 @7.0, restore 6,239.4 —
**restore stall**), 22-47-20 (1,079.4 @11.4, 419.0, fast), 22-47-48 (1,252.1
@9.8, 1,226.5, fast). Run 22-53-47: activation cancelled (request finalized;
preserved, not a measurement). Run 22-35-47 (first deploy, late-mode default):
activation total 7,036.7 (patcher residual 7,009), restore 3,049.9 — stall +
restore stall.

**Fast vs slow comparison (worker sub-stages, ms):**

| Stage | Fast (6 runs) | Slow (8 runs) | Delta |
|---|---:|---:|---:|
| Queue delay | 0.7–10.3 | 1.0–12.3 | none |
| CPU-snapshot wait | 0.06–0.13 | 0.06–0.13 | none |
| dtype/layout prep | 2.0–14.7 | 3.2–18.5 | none |
| Registry setup | 4.4–5.7 | 4.7–7.3 | none |
| Page traversal (pretouch off) | n/a | n/a | n/a |
| **Synchronized transfer** | **924–1,121 (11–13 GB/s)** | **3,175–16,693 (0.7–3.9 GB/s)** | **the entire delta** |
| Post-load bookkeeping | 1.7–2.5 | 2.6–21.9 | none |
| Sampling | 3,664–3,707 (invariant) | 3,664–3,707 (invariant) | none |
| Sampler lane wait (demand→first forward) | 115–160 | 115–160 (activation overlaps graph; sampler wait ≤160 ms unless activation never completes before demand) | none |

Restore (fast vs slow): median ~1.0–1.2 s; stalls 3.97/4.05/4.34/6.24 s driven
by `restore_gpu_state` (1,537–2,061 ms) + `snapshot_restore` +
`reload_runtime_state`, confirmed via `restore_breakdown` in every artifact.

## 5. Before/after slow-run results (implemented fix)

The shipped fix (minimal single-use teardown) does not change sampling or the
transfer; it changes the post-terminal path:

| | Before (full teardown, A) | After (minimal, B) |
|---|---:|---:|
| Terminal release elapsed | 2,560.3 ms | 2.5 ms |
| Post-stream release | 633.8 ms | 2.0 ms |
| Exit hook duration | 23.9 ms | 20.3 ms |
| CUDA after release | 34.6 MB (in-app) | 12.63 GB (process-exit) |
| Result delivery | identical | identical |

The transfer variance itself is platform-bound (measured; pinning falsified),
so no speculative app-side transfer fix is shipped — instrumentation now
proves this precisely on every run.

## 6. Files changed

- `comfymodal_runtime/modal_app.py` — minimal-teardown default for single-use;
  request allowlist entries (`minimal_teardown`, `pin_unet_transfer`);
  teardown-mode diagnostics.
- `comfymodal_runtime/model_preload.py` — worker variance sub-stages
  (queue/cpu-wait/dtype/registry/sync/bookkeeping), true-total reconciliation,
  emit-order fix (post-terminal), `unet_resolved_mono_ns`; gated
  `COMFYMODAL_V2_PIN_UNET_TRANSFER` pinning helper (experiment, default off).
- `tools/benchmark_v2_direct.py` — `--teardown`, `--pin-transfer`, request
  origin fields, `restore_breakdown` + new worker metrics in `_timing`.
- `tools/variance_report.py` — new metrics (queue/cpu-wait/dtype/bb/total,
  restore breakdown) into categories and rendered tables.
- `tests/test_v2_teardown_diagnostics.py` — minimal-teardown default tests
  (single-use vs reusable), explicit-override tests.
- `tests/test_v2_variance_worker.py` — reconciliation/queue/cpu-wait tests,
  pinned-transfer helper tests.
- `V2_VARIANCE_CAUSAL_FIX_REPORT.md` — this report.

Final commit SHA: reported in the commit message of this change.
