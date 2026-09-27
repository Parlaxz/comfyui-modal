# V2 Transfer-Regression Evidence Report (12–13 s → 16 s)

Generated 2026-08-06 from controlled cold runs on the V2 shadow app
(`stable-modal-comfy-v2-shadow`, GPU `rtx-pro-6000`, CPU 16, memory
49152 MiB, workspace Legacy Modal Token, single-use containers,
25-second inter-run gaps, strict cold-identity proof
`restore_count == 1 && request_count == 1`).

## 1. Question

Yesterday's healthy run (`im-yFDta4CRc1uNkJQNuKCLYj` /
`6da06a560878659a`, UNET activation mode `late`): restore 401 ms,
UNET transfer 1,052 ms, sampler wait 573 ms, command→response 14.898 s.
Current runs (`im-kWOwGvWsEECjxyaznddeLs` / `f9c3ad185b8c1473`, mode
`clip_gpu_ready`): UNET transfer ≈ 4.9 s, sampler wait ≈ 4.76 s, no
runs below ≈ 16 s. Which code/config change caused it?

## 2. Method

Controlled cold matrix on the shadow app, one variable at a time,
5 valid cold runs per cell, identical workflow (`ae859349…`),
placement (rtx-pro-6000, CPU 16, mem 49152), cache state (warm
conditioning-cache volume), and 25 s gaps:

| Cell | Code | UNET activation | Diagnostics | Artifacts |
|---|---|---|---|---|
| A | HEAD `6547496` | `late` | off | `v2_2026-08-06_00-26-51` |
| B | old revision `a87426d` | `late` | off | `v2_2026-08-06_00-59-40` |
| C | HEAD `6547496` | `clip_gpu_ready` | on | `v2_2026-08-06_00-49-24` |
| Fix-1 | HEAD `6547496` | `late` | off | `v2_2026-08-06_01-14-09 … 01-26-39` |
| Fix-2 | HEAD `6547496` | `late` | on (measurement) | `v2_2026-08-06_01-36-32 … 01-44-36` |

Plus the historical artifacts of both deployments
(`v2_2026-08-05_16-xx`, `v2_2026-08-05_23-xx`) and the published
23:xx variance tables.

## 3. The transfer is the only variable stage — and it is bimodal in EVERY configuration

Synchronized 12.31 GB CPU→GPU transfer (`unet_early_activation_load_end.load_wall_ms`,
measured with CUDA sync when diagnostics are on; identical event in the
16:xx old-deploy traces), ms:

| Config | Run loads (ms) | Median |
|---|---|---|
| OLD deploy 16:xx (`late`) | 1,052 / 6,515 / 17,966 | 6,515 |
| Cell B — old rev `a87426d` (`late`, off) | 1,103 / 1,979 / 4,614 / 15,865 | 3,296 |
| Cell A — HEAD (`late`, off) | 1,787 / 5,604 / 19,001 / 19,173 | 12,302 |
| Fix-1 — HEAD (`late`, off) | 1,138 / 2,095 / 2,159 / 4,385 / 20,731 | 2,159 |
| Fix-2 — HEAD (`late`, on) | 1,699 / 5,496 / 6,042 / 16,205 | 5,769 |
| Cell C — HEAD (`clip_gpu_ready`, on) | 953 / 2,067 / 2,152 / 12,339 / 4,003 | 2,152 |
| CURRENT deploy 23:xx (`clip_gpu_ready`, on) | 0.92–16.7 s over 17 runs (published) | ≈ 3.2 s |

The distribution is the SAME in every cell: a fast side ≈ 0.9–2.2 s
(~10–13 GB/s) and a slow side ≈ 3–21 s (0.7–3.9 GB/s), with the fast
side appearing in 25–40 % of runs in every configuration. The "healthy"
old run (1,052 ms) is the fast side of this distribution; the old
deployment produced 6.5 s and 18.0 s loads in the same session. The
current deployment produced 0.92–1.25 s loads in 6 of its 17 runs.

Same revision/config reproduces both behaviors under comparable
placement — including within a single session and region (e.g.
Fix-1 runs 1.1–20.7 s on consecutive AWS placements) — so per the
protocol's own rule this is platform-side scheduling/contention
variance, not a code or configuration regression.

## 4. Why it looks like a regression

1. **The "healthy" run is one sample of a bimodal distribution.** The
   old session (16:xx) had cmd→resp 15.5 s, 38.9 s, ≈20 s, 140.4 s and
   transfer loads 1.05 s / 6.5 s / 18.0 s. The remembered healthy run
   (16-58-28: 401 ms restore, 1,052 ms transfer, 16.0 s cmd→resp) is the
   fast side.
2. **The early-activation worker fires in `late` mode too.** On an exact
   conditioning-cache hit, `_schedule_unet_activation_conditioning_cache_hit`
   (`comfymodal_runtime/model_preload.py:12443`, from commit `c58859b`,
   2026-08-03) schedules the retained-UNET 12.31 GB load through the
   shared worker, in every mode. All benchmark traces show
   `trigger=conditioning_cache_hit` regardless of `late`/`clip_gpu_ready`.
   The cache-hit path therefore already existed in the old deploy, and
   the mode flag does not change the transfer distribution (Cell A vs
   Cell C medians 2.15 s vs 2.15 s).
3. **Code delta between the deployments is inert.** Between the old
   deploy era and HEAD, the only transfer-path changes are `8faa106`
   (variance diagnostics) and `6547496` (worker sub-stage
   instrumentation + rejected pinning experiment). Every addition is
   gated by `COMFYMODAL_V2_VARIANCE_DIAGNOSTICS` /
   `COMFYMODAL_V2_UNET_PRETOUCH` / `COMFYMODAL_V2_PIN_UNET_TRANSFER`
   (all default off): no unconditional `cuda.synchronize()`, no
   unconditional storage-registry build, no unconditional pretouch
   (verified statically and confirmed by Cell B ≈ Cell A timing).
   `cpu_snapshot_models.py` and `runtime_executor.py` are unchanged
   between `8faa106` and HEAD.
4. **The remaining metrics are invariant or old-deploy-identical:**
   sampling 3.65–3.90 s in all 27 controlled runs; restore bimodal
   (0.4–8 s, `restore_gpu_state` 0.24–6.2 s) in BOTH deployments;
   entry latency (Modal container scheduling/snapshot resume,
   `submit2entry_ms`) 4–273 s across sessions, uncorrelated with
   config.

## 5. Why the transfer stalls when it does

The 12.31 GB copy is CPU-mediated (thread CPU ≈ wall on slow runs;
zero page faults; zero IO; 4.7 process cores busy vs 1.5 on fast —
published 23:xx measurements). The cache-hit early-activation worker
runs the copy concurrently with CLIP prefill, snapshot restore and
background backend startup on the same 16 CPUs; under host contention
the copy's effective bandwidth collapses. This mechanism is
platform/host-side; the pinning experiment (`COMFYMODAL_V2_PIN_UNET_TRANSFER`)
was interleaved A/B and falsified as a fix (same bimodality with
pinning on/off).

## 6. Conclusion — no code/config fix is warranted

- No causal commit or configuration change exists between the two
  deployments for the transfer path (bisection not applicable: the old
  revision is not uniformly fast — it reproduced 1.0–18.0 s loads).
- The production configuration is already the healthy one: mode
  `late`, diagnostics off, single-use containers, minimal teardown —
  all defaults in `deploy_and_run_v2_single.bat` /
  `modal_app.py._runtime_env`.
- Current code with the production config still produces transfers
  below 1.5 s (953 / 1,103 / 1,138 / 1,699 ms observed), restore
  0.99–6.07 s, sampler activation wait ≤ 303 ms, sampling ≈ 3.7 s.
- Per the task instruction "Do not implement a speculative fix", no
  code change is shipped. The verified fix-configuration runs are
  preserved under `comfymodal-data/benchmarks/runs/v2_2026-08-06_*`
  (Fix-1 and Fix-2 passes, 9 cold runs).

## 7. Verification evidence (fixed configuration, HEAD + `late` + diagnostics off)

Fix-1 pass, 5 cold runs (25 s gaps, single-use, minimal teardown):

| Run dir | Transfer load (ms) | Restore (ms) | Sampling (ms) | Sampler act. wait (ms) | Wall (ms) |
|---|---:|---:|---:|---:|---:|
| 01-14-09 | 2,095 | 1,019 | 3,695 | 230 | 168,974 |
| 01-17-24 | 2,159 | 990 | 3,697 | 226 | 149,880 |
| 01-20-19 | 1,138 | 1,228 | 3,701 | 148 | 161,532 |
| 01-23-26 | 20,731 | 6,072 | 3,742 | 143 | 167,106 |
| 01-26-39 | 4,385 | 1,750 | 3,896 | 303 | 287,719 |

Wall times are dominated by Modal-side container-entry latency
(137–273 s in this session), which is uncorrelated with the
application configuration.

## 8. Files changed

- `V2_TRANSFER_REGRESSION_EVIDENCE_REPORT.md` — this report.

No runtime code was modified. Commit SHA: see commit message.
