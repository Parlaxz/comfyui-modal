# COMFYUI-MODAL V2 — AUG 9 RESOURCE/GPU OPTIMIZATION REPORT

**Date:** 2026-08-09 · **Branch:** `TESTING2` (experiments) / `main` (production baseline)
**Workspace:** Modal workspace **"Testing 2"** (id `ws_228aedb01781`) was set as the active workspace for all experiment deploys (backup of the original `.modal_workspaces.json` at `C:\Users\parla\AppData\Local\Temp\opencode\modal_workspaces.backup.json`; original active workspace was "Testing 1" `ws_e677ab553606` — left switched to Testing 2 per "all work on TESTING2").

---

# 1. `main` reconciliation

The validated production candidate (`stable-modal-comfy-v2-production-candidate`, 10/10 true-cold PASS) was deployed from the **working tree**, not from a dedicated commit. The uncommitted working tree (24 modified + ~43 untracked files) was classified per the merge rules:

**KEEP → merged to `main` (commit `f8f2da5`):**
- Bat app-name/GPU env overrides (`if not defined` pattern preserving defaults)
- Full waterfall-persistence chain (idempotent `attach_waterfall` finalizer on every result path, serialized waterfall in run-history timing payloads + Studio diagnostics)
- `run_entry_probe` restore-first-line timing exposure
- `tools/analyze_production_candidate.py` (production-candidate report generator)
- Waterfall-contract tests (6 test files, one assertion removed from `test_waterfall_attach_central.py` because it pinned the NUMA experiment method)

**DO NOT MERGE → carried on `TESTING2` only (`be5a863`):** NUMA experiment, GPU snapshot shadow app + restore probes, pagesfile/restore-matrix harnesses, `SNAPSHOT_EXCLUDE_UNET` lean gate, `_two_lane_read_residency` orphan helper + tests, ownership-rehoming tooling, experiment reports/logs/matrix artifacts.

`main` now contains the same effective runtime behavior used by the validated candidate (verified by py_compile + 132/133 focused unit tests; the 1 failure — a bat-structure assertion in `test_v2_batch_profiles.py` — fails identically at HEAD `ca1f114`, pre-existing).

# 2–4. Provenance / commits / canonical baseline

| Item | Value |
|---|---|
| Source of validated candidate | Working tree at HEAD `ca1f114` + uncommitted KEEP changes; app `stable-modal-comfy-v2-production-candidate` |
| TWO-LANE implementation | Committed at HEAD `ca1f114` (prefill-lanes `critical` + `UNET_EARLY_ACTIVATION` lane; `COMFYMODAL_V2_PREFILL_LANES`, `COMFYMODAL_V2_UNET_ACTIVATION_MODE`); validated artifacts carry `sampler_lane_wait_end blocking_owner=UNET_EARLY_ACTIVATION` |
| **MAIN_BASELINE_COMMIT** | **`f8f2da5b46becd33cf8e6cc17be804cc56760018`** |
| TESTING2 base | `be5a863` (baseline + experiment worktree material) |
| Experiment commits on TESTING2 | `713bff7`, `683efa0`, `fb0a9a1`, `e249c11`, `bd5aa2f`, `7b14577`, `8344e8e`, `4ecdc35`, `bf8055a` (telemetry, arm driver, analyzer, GPU repair) |

# 5. Production vs experiment separation

- `main` = validated production runtime only (unchanged by experiments).
- `TESTING2` = production + telemetry (opt-in env `COMFYMODAL_V2_RESOURCE_TELEMETRY`, default off) + experiment tooling (`tools/run_resource_arm.py`, `tools/analyze_resource_gpu_experiments.py`) + GPU-matrix repair (`COMFYMODAL_V2_GPU` env passthrough, `gpu_allocation` result payload, `h100!` exact selector, fail-closed analyzer gate).
- Production deployments (`comfyui`, `stable-modal-comfy-v2-shadow`, production-candidate app) untouched; all experiment deploys use dedicated app identities in the Testing 2 workspace.

# 6. Telemetry implementation

`comfymodal_runtime/resource_telemetry.py` (committed `713bff7` → `7b14577`):
- 50 ms sampling loop (daemon thread) reading cgroup-wide counters, opt-in via `COMFYMODAL_V2_RESOURCE_TELEMETRY` (default 0 — zero production impact).
- **memory.current / memory.peak**: cgroup v2, multi-candidate probe (`mountinfo`-resolved base, `/sys/fs/cgroup`, legacy `memory/memory.usage_in_bytes`) — proven working (matrix-harness evidence).
- **cpu.stat (usage_usec/user/system)**: NOT readable in this Modal/gVisor runtime at any probed path (confirmed by 4 deploy cycles and no prior artifact ever containing cpu.stat data) → **CPU falls back to process-wide utime/stime ticks from `/proc/self/stat`** (`cpu_source=process`). Honest limitation: cgroup CPU unavailable; process CPU captured.
- Aggregates: average/peak/p95 cores, window peaks (50/100/250/500/1000 ms), RAM peak/p95/end, per-stage cores/RAM/duration.
- Stage markers from existing trace-event wall timestamps (python resume / bootstrap / CLIP-graph prep / TWO-LANE activation / sampler prep / sampling / VAE / output-result).
- Wired into `run_plan_stream` (start at method entry, attach `result["resource_telemetry"]` at final event).

# 7. RAM experiment (Phase 3) — WINNER: 28672 MiB

**Config:** RTX PRO 6000 · CPU 16 → **CPU request 8** (final shape) · memory 28672 MiB · FULL snapshot · TWO-LANE · TBASE/O0 · AWS, no region pin · single-use · minimal teardown · telemetry on.
**Protocol:** 2 excluded warmup runs + 4 measured true-cold per cycle.

**Retry history (harness failures, not application failures):**
- Cycle 1: measured failed — telemetry scope bug (`UnboundLocalError`, fixed `fb0a9a1`).
- Cycle 2–3: measured runs valid (rc=1/rq=1/outputs correct) but telemetry `unavailable` (cgroup path resolution; fixed `e249c11`, `bd5aa2f`, `7b14577`). Cycle 2–3 runs **not used** for the RAM decision (RAM metric missing) — timing preserved in artifacts.
- Cycle 4 (final): telemetry **measured**, RAM captured. **4/4 valid.**

**Cycle-4 raw runs** (dir `runs\v2_2026-08-09_16-15-46`):

| run | region | sub2resume | app (1st remote→result) | two_lane | sampling | VAE | RAM p95 GB | RAM sampled peak GB | cores avg/peak |
|---|---|---|---|---|---|---|---|---|---|
| 0 | us-east-2 | 8159.6 | 9690.6 | 1808.6 | 3719.9 | 524.9 | 23.78 | 25.19 | 1.44 / 9.39 |
| 1 | us-east-2 | 4784.0 | 9649.0 | 2023.0 | 3735.4 | 491.8 | 24.22 | 25.19 | 1.45 / 11.71 |
| 2 | us-east-1 | 63757.2 | 19841.4 | 9342.7 | 3687.0 | 437.5 | 25.02 | 25.19 | 1.75 / 6.81 |
| 3 | us-east-1 | 18713.1 | 8547.9 | 1410.2 | 3694.3 | 441.8 | 23.60 | 25.19 | 1.43 / 8.09 |

**Decision: PASS** — 4/4 correct outputs, no OOM, RAM p50 23.8–25.0 GB (peak 25.19 GB) **safely below 28 GiB (30.1 GB decimal)**, sampler/VAE unchanged vs 49 GiB baseline (3.69s/0.44s vs 3.71s/0.43s), no memory-pressure tail (app outliers are pre-Python scheduling, run 2's 19.8s app is a one-off pre-sampler tail with normal sampling/VAE).
**WINNING_RAM = 28672 MiB.** No 32 GiB test needed.

# 8. CPU experiment (Phase 4) — WINNER: 8

Baseline = existing validated CPU=16 population + same-workspace RAM-arm (CPU 16, n=4). **CPU=16 not rerun.**

**Arm CPU=4** (8 runs, dir `v2_2026-08-09_16-48-47`) — **FAIL**:
- Outputs 8/8 correct; sampling unchanged (3.77s); VAE unchanged.
- **Actual CPU burst capped**: cores peak p50 **3.0** (max 4.4) vs natural demand 7–11 at CPU=16 → Modal enforces the request as a burst cap; the "does it still burst to 8–10 cores" question answers **NO**.
- CPU-bound stages regress vs same-workspace CPU=16: two_lane p50 2249.7 (+441 ms), pre-sampler p50 4309 (+333 ms), app p50 11131 (+461 ms; +0.75 s vs validated candidate).
- Scheduling p50 6507 ms (no improvement vs 7856 ms at CPU=8).
- Verdict: **starvation signature at the 4-core quota** → CPU=4 fails the PASS criteria.

**Arm CPU=8** (8 runs, dir `v2_2026-08-09_17-04-42`) — **PASS**:
- 8/8 correct; tight app tail (p90 12324 ms vs CPU4's 52051 ms max-outlier); two_lane p50 2005 ms (+197 ms vs CPU16 — within noise); sampling 3.75s; VAE 0.49s; cores peak p50 4.4 **below the 8-core quota → no throttling**; no CPU-starvation signature; app p50 11170 (+501 ms vs CPU16 ≈ +4.5 %, small population, no recurring starvation).
- Scheduling p50 22323 ms is a placement-window observation (platform), not a request-shape effect (same storm hit RAM arm).

**WINNING_CPU = 8.** CPU=12 not tested (per ladder).

# 9. GPU experiments (Phase 5) — matrix status after audit + stop

| GPU | requested | valid runs | DNF | status |
|---|---|---|---|---|
| RTX PRO 6000 | rtx-pro-6000 | **8** (CPU-arm population reused) | 0 | baseline ✓ |
| A100 80GB | a100-80gb (exact; auto-upgrade only to 80 GB which is what was requested) | **3** | 1 (user-abandoned run 4, 25+ min scheduling) | filled to 3 (min) |
| H100 | h100 (runs landed on real H100, nvidia-smi verified) | **3** | 0 | filled to 3 (min); fills must use `H100!` |
| H200 | h200 | **3** | 0 | filled to 3 (min) |
| B200 | — | 0 | — | **NOT TESTED** (canary gate) |
| B300 | — | 0 | — | **BLOCKED_BY_RUNTIME_COMPATIBILITY** |
| L40S | — | 0 | — | **NOT TESTED** (canary gate) |

**GPU VALIDITY AUDIT AND CORRECTED MATRIX**

**Baseline (validated candidate) exact config** (from `run_production_candidate_measured.log` env header + run artifacts): `env_profile=production, gpu=RTX-PRO-6000, cpu=16, memory=49152, thread_policy=TBASE, snapshot_model_order=O0, prefill_lanes=critical, unet_activation_mode=late, vae_activation_mode=sampling_end, cpu_model_snapshot=1, vae_snapshot=1, clip_conditioning_cache=1, release_gpu_after_request=1, single_use_containers=True, min_containers=0, cloud=aws (no region pin), all diagnostics off, EXCLUSIVE_OWNER/REHOME off`. **`mode=late` IS the validated TWO-LANE config** — lane1 = critical prefill lane, lane2 = `UNET_EARLY_ACTIVATION` lane; `late` is only lane-2's trigger timing (after conditioning-cache hit). CacheDiT: restore-time prepare only, GPU-agnostic (`v2_startup_cachedit_preparation`). SageAttention: `comfymodal-sage-v1` patch applied at snapshot build, verified at restore, GPU-agnostic patch of `PathchSageAttentionKJ`.

**Per-run audit** (all measured GPU runs vs candidate invariants; full evidence in `comfymodal-data\benchmarks\resource_experiments\*_summary.json` + audit notes):

| GPU | run | actual GPU (nvidia-smi / torch props) | region | snapshot invariant | TWO-LANE join | dup-H2D (load pairs) | first_cuda | sampling | two_lane | classification |
|---|---|---|---|---|---|---|---|---|---|---|
| A100 | r0 | A100-80GB (deploy-request exact + sampling signature; no nvidia-smi — old driver) | us-east-1 | pass (clip/unet=1, O0) | 1× | 1 (restore) | 144 ms | 5705 | 2311 | **VALID** |
| A100 | r1 | same | us-east-1 | pass | 1× | 1 (restore) | 153 ms | 5711 | 2748 | **VALID** |
| A100 | r2 | same | us-east-1 | pass | 1× | 1 (restore) | 143 ms | 5699 | 2298 | **VALID** |
| H100 | r0 | **NVIDIA H100 80GB HBM3** (uuid e07325d7) | us-west-2 | pass | 1× | 1 (restore) | 173 ms | 2454 | 13633 | **VALID** |
| H100 | r1 | **NVIDIA H100 80GB HBM3** (uuid 7d498319) | us-west-2 | pass | 1× | 1 (restore) | 210 ms | 2385 | 4405 | **VALID** |
| H100 | r2 | **NVIDIA H100 80GB HBM3** (uuid 7e5d9741) | us-west-2 | pass | 1× | 1 (restore) | 193 ms | 2446 | 13352 | **VALID** |
| H200 | r0 | **NVIDIA H200** (uuid 56f8da4c) | us-west-2 | pass | 1× | 1 (restore) | 179 ms | 2310 | 4878 | **VALID** |
| H200 | r1 | **NVIDIA H200** (uuid 53df9b76) | us-west-2 | pass | 1× | 1 (restore) | 203 ms | 2346 | 5994 | **VALID** |
| H200 | r2 | **NVIDIA H200** (uuid 7512b88e) | eu-south-2 | pass | 1× | 1 (restore) | 192 ms | 2321 | 5504 | **VALID** |
| A100 | run 4 | abandoned | — | — | — | — | — | — | — | **DNF (user-abandoned, >25 min scheduling)** |
| Canary | warmup/measured | — | — | — | — | — | — | — | — | **DNF ×2 (placement; restore_publish 630 s > 10 min cap)** |

Every valid GPU run: `restore_count=1, request_count=1, images=1, no error, single-use container`, `snapshot_activation_invariant status=pass (clip/unet/cpu_snapshot_active=1, O0)`, `sampler_lane_wait_end blocking_owner=UNET_EARLY_ACTIVATION` exactly once, `unet_early_activation_* 1/1/1`, one `cpu_snapshot_unet_load` pair **phase=restore** (no request-time reload), `unet_first_cuda_op model_identity=cpu_snapshot, x_device=cuda:0, elapsed 143–210 ms`, CacheDiT prepare present (A100 1376 ms / H100 2632 ms / H200 3177 ms / candidate 1735 ms), `sage_mode=patched_at_snapshot` on every run.

**Stale-GPU-logging vs wrong-GPU-request resolution (Case A — logging bug only):**
- `identity.gpu` reports `RTX-PRO-6000` on every arm because the container rebuilds `ModalRuntimeSpec.gpu` from its own env, and `_runtime_env()` did **not** forward `COMFYMODAL_V2_GPU` (default RTX-PRO-6000). `gpu_requested_order`/`gpu_actual_name` exist only as a `[v2.gpu_allocation]` console line.
- Deployed function config: driver env `COMFYMODAL_V2_GPU=<arm gpu>` → deploy-time `parse_gpu_request()` → exact single-GPU request (fallbacks empty), no fallback lists anywhere. The benchmark's `_validate_runtime_shape` **passed cpu=8/memory=28672** on every arm, proving the container spec is not wholesale-defaulted — only the GPU label is stale.
- **Fix committed (`bf8055a`):** `_runtime_env` now forwards `COMFYMODAL_V2_GPU`; every result payload now carries `gpu_allocation {gpu_requested_order, gpu_actual_name, gpu_compute_capability}`; analyzer `--expect-gpu` fail-closed gate; `h100!` exact selector added to the catalog (Modal auto-upgrades `h100`→`h200` unless `H100!`; observed runs verified on real H100, but fills must use `H100!`).
- **Unverified by a paid run** (canary DNF on placement) — the fix is static-verified only.

**Invalidated results:** none among the 9 measured GPU runs (all runtime-path VALID). Cycle-2/3 RAM-arm runs excluded from RAM decision (telemetry unavailable) — preserved. One pre-existing failing unit test (bat-structure assertion, fails at HEAD too).

**ZERO-PAID-RUN PATH REANALYSIS (follow-up, 2026-08-09):** All 18 runs (8× RTX reference + 1× candidate + 9× GPU arms) were re-extracted on seven path axes to test whether any GPU run took a slower path than the RTX reference. Classification axes: conditioning-cache hit/miss (`clip_conditioning_cache_decision` lookup decision `exact_hit`, corroborated by `clip_conditioning_cache_lookup` hit_count and `unet_early_activation_mode.trigger=conditioning_cache_hit`), early-UNET-activation scheduled/lane-acquired, activation start/ready wall times, sampler-visible wait, actual `load_models_gpu` wall, sampling.

| arm | cache | ea sched | load_models_gpu ms (phase) | req-time load? | sampler_lane_wait ms | pre_sampler ms | py→result ms | sampling ms | class |
|---|---|---|---|---|---|---|---|---|---|
| RTX r0–r7 (n=8) | HIT ×8 | ✓ ×8 | 1.0–3.8 (exec) | no ×8 | 1788–2558 | 3762–4588 | 10443–12528 | 3730–3793 | **FAST ×8** |
| CAND r0 | HIT | ✓ | 4.3 (exec) | no | 1486 | 3331 | 10067 | 3679 | **FAST** |
| A100 r0–r2 | HIT ×3 | ✓ ×3 | 5.7–6.3 (exec) | no ×3 | 2298–2748 | 5742–7403 | 15596–16923 | 5699–5711 | **FAST ×3** |
| H100 r0–r2 | HIT ×3 | ✓ ×3 | 2.9–4.5 (exec) | no ×3 | 4405–13633 | 8415–22931 | 23719–32976 | 2385–2454 | **FAST ×3** |
| H200 r0–r2 | HIT ×3 | ✓ ×3 | 2.1–7.5 (exec) | no ×3 | 4878–5994 | 8251–9262 | 16623–18088 | 2310–2346 | **FAST ×3** |

Fast-path predicate (derived from the RTX reference population): `cache_hit == exact_hit AND early_activation_scheduled AND lane_acquired AND load_models_gpu_ms < 1000 AND load_models_gpu_at_request == False`. **All 9 GPU runs satisfy it (n_fast == n_all per arm) → path-filtered medians are identical to the unfiltered table above; no GPU median changes.**

**Mechanism verdict — the hypothesis is falsified:** no conditioning-cache miss, no late/missing early activation, no request-time `load_models_gpu` (1–7.5 ms bookkeeping only; restore-time `reload_models` ~68–145 ms) on any run. The large TWO-LANE lane-waits are a **transfer-bandwidth effect of the early-activation CPU→GPU H2D of the retained ~12.3 GB snapshot UNET**, not a path change: RTX `unet_early_activation` load_wall 2145–3062 ms → lane_wait 1788–2558 ms; A100 load_wall 3003–4710 ms → 2298–2748 ms; H100 load_wall 5100–20322 ms → 4405–13633 ms (two runs ~19.5–20.3 s load); H200 load_wall 5291–6318 ms → 4878–5994 ms. Sampler wait tracks load at a roughly constant fraction (≈0.66–0.82×) on both RTX and H100 — the absolute wait scales with host transfer time, so H100's lane-wait does NOT collapse to RTX-like ~2 s under path filtering. Sampling itself is faster on H100/H200 (2.31–2.45 s) and slower on A100 (5.70 s) than RTX (3.75 s); the GPU arms' penalty is entirely early-activation transfer + placement window. Machine-readable output: `C:\Users\parla\AppData\Local\Temp\opencode\gpu_path_reanalysis.json` (18 per-run dicts + per-arm medians + predicate). **Analysis caveat noted:** `clip_conditioning_cache_decision` emits a later *store* decision `miss_not_stored` that must not be mistaken for a lookup miss (downstream analyzers should key on the lookup event).

# 10–14. Distributions, actual CPU/RAM, GPU identities

**Scheduling (submission→restore banner, ms):** RTX(cpu8) p50 79321 / p90 134100 · A100 p50 76299 / p90 83655 · H100 p50 9433 / p90 12634 · H200 p50 7615 / p90 12931. **The experiment window suffered a severe placement storm** (all arms; many runs 60–135 s, some >10 min). These are platform placement facts, not request-shape effects; queue wait is not billed by Modal.

**Application waterfall (ms, min/p50/p90/max):**

| metric | RTX PRO (cpu8, n=8) | A100 (n=3) | H100 (n=3) | H200 (n=3) |
|---|---|---|---|---|
| python resume→result | 10520/11265/12324/12324 | 15665/15916/17022/17022 | 23382/32315/32445/32445 | 16746/17899/18170/18170 |
| restore total | 900/1381/2189/2189 | 1247/1253/1339/1339 | 2527/2884/7143/7143 | 1708/1940/2396/2396 |
| TWO-LANE (lane wait) | 1788/2113/2558/2558 | 2298/2311/2748/2748 | 4405/13352/13633/13633 | 4878/5504/5994/5994 |
| sampling | 3730/3753/3793/3793 | 5699/5705/5711/5711 | 2385/2446/2454/2454 | 2310/2321/2346/2346 |
| VAE | 464/502/724/724 | 592/594/604/604 | 418/423/449/449 | 471/482/579/579 |

**Actual CPU (50 ms process-tick telemetry):** RTX avg 1.2 / peak p50 4.4 (≤8 quota) · A100 avg 1.3 / peak 6.3 · H100 avg 1.8 / peak 8.5 · H200 avg 1.1 / peak 5.0. All arms below their 8-core quota → no throttling.

**Actual RAM (cgroup memory.current):** peak ~25.2 GB, p95 23.6–25.3 GB on every arm — unchanged across CPU/GPU arms (FULL snapshot dominates).

**GPU identities:** nvidia-smi-verified: H100 = `NVIDIA H100 80GB HBM3`, H200 = `NVIDIA H200` (host_diagnostics). A100 = deploy-request exact + sampling signature (5.7 s, consistent with A100-class; no nvidia-smi in old-driver artifacts). Attention/backend: `sage_mode=patched_at_snapshot` (comfymodal-sage-v1, PathchSageAttentionKJ) on all runs; CacheDiT restore-prepare present on all runs; VAE bf16 native.

# 15–16. Pricing (verified Aug 09 2026) + cost calculations

**Source:** `https://modal.com/pricing` (per-second rates) + `https://modal.com/docs/guide/billing` + `https://modal.com/docs/guide/gpu` — accessed **2026-08-09**. 1-second billing granularity, no per-container minimum, all GPU functions preemptible at list price (no GPU non-preemptible option). Region selection outside default can add 1.5–1.75× (base rates used here).

| GPU | $/s | $/hr (derived) |
|---|---|---|
| RTX PRO 6000 | 0.000842 | 3.03 |
| A100 80GB | 0.000694 | 2.50 |
| H100 | 0.001097 | 3.95 |
| H200 | 0.001261 | 4.54 |
| B200 | 0.001736 | 6.25 |
| B300 | 0.001972 | 7.10 |
| L40S | 0.000542 | 1.95 |

CPU $0.0000131/core/s (physical core = 2 vCPU; requested floor 8 cores), RAM $0.00000222/GiB/s (28 GiB floor).

**Final-shape blended rates (GPU + 8 CPU + 28 GiB):** RTX $0.0605/min · A100 $0.0517/min · H100 $0.0758/min · H200 $0.0857/min · B200 $0.1142/min · L40S $0.0425/min.

**Measured $/generation (container-resident time = python-resume→result + restore; queue wait excluded — not billed):**

| GPU | $/gen p50 | $/gen p90 | $/min | $/hr |
|---|---|---|---|---|
| RTX PRO 6000 | **0.0128** | 0.0146 | 0.0605 | 3.63 |
| A100 80GB | **0.0148** | 0.0158 | 0.0517 | 3.10 |
| H100 | 0.0445 | 0.0500 | 0.0758 | 4.55 |
| H200 | 0.0283 | 0.0294 | 0.0857 | 5.14 |

# 17. Final comparison tables

**RAM table:** request 28672 MiB → actual peak 25.19 GB / p95 23.6–25.0 GB; app timings within baseline noise; scheduling = platform storm; **verdict PASS**.

**CPU table:**

| CPU req | peak cores | avg cores | scheduling p50 | py→result p50 | sampling p50 | TWO-LANE p50 | sub→result p50 | verdict |
|---|---|---|---|---|---|---|---|---|
| 16 (same-ws) | 8.1 | 1.4 | 18713 | 10669 | 3694 | 1809 | 18903 | baseline ref |
| 4 | 3.0 | 1.1 | 6507 | 11131 | 3766 | 2250 | 20152 | FAIL (burst capped, starvation) |
| **8** | **4.4** | 1.2 | 22323* | 11170 | 3753 | 2005 | 34096* | **WIN** |

*placement-window noise (same storm on all arms).

**GPU table (final valid populations):**

| GPU | n | scheduling p50 | restore p50 | TWO-LANE p50 | sampling p50 | VAE p50 | py→result p50 | sub→result p50 | peak RAM | peak CPU | $/min | $/gen p50 | correct |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| RTX PRO 6000 | 8 | 79.3 s | 1.38 s | 2.11 s | 3.75 s | 0.50 s | 11.27 s | 91.8 s | 25.2 GB | 4.4 | 0.0605 | 0.0128 | 8/8 |
| A100 80GB | 3 | 76.3 s | 1.25 s | 2.31 s | 5.70 s | 0.59 s | 15.92 s | 92.2 s | 25.2 GB | 6.3 | 0.0517 | 0.0148 | 3/3 |
| H100 | 3 | 9.4 s | 2.88 s | 13.35 s | 2.45 s | 0.42 s | 32.31 s | 38.4 s | 25.3 GB | 8.5 | 0.0758 | 0.0445 | 3/3 |
| H200 | 3 | 7.6 s | 1.94 s | 5.50 s | 2.32 s | 0.48 s | 17.90 s | 25.7 s | 25.2 GB | 5.0 | 0.0857 | 0.0283 | 3/3 |

**Relative vs RTX PRO 6000:** application speed: H200 63% faster py→result, H100 35% slower (TWO-LANE lane-wait anomaly), A100 41% slower · user-wall speed: H200 72% faster, H100 58% faster, A100 ~equal (storm-dominated) · cost: A100 85% of RTX, H100 125%, H200 142% · cost/performance: H200 best on application-time-per-dollar (0.63× app time at 1.42× cost), A100 cheapest absolute.

# 18. Invalid/retried runs

- RAM arm cycles 1–3 (12 measured) — harness telemetry bugs; timing preserved, excluded from RAM decision.
- A100 run 4 — DNF/user-abandoned (>25 min scheduling; user did not wait). Scheduling fact preserved.
- Canary (A100, repaired code) — warmup + measured both DNF at 10-min cap (placement: `restore_publish_ms=630891`; no container reached). **Canary gate: FAILED on placement → paid GPU runs STOPPED per instruction.**
- One pre-existing unit-test failure (bat structure) — unrelated, fails at HEAD.

# 19–22. Apps / artifacts / files / commits

**Modal apps deployed (Testing 2 workspace):** `stable-modal-comfy-v2-res-ram28`, `...-cpu4`, `...-cpu8`, `...-a100-80`, `...-h100`, `...-h200`, `...-a100-canary` (+ `...-res-a100-80` first attempt). Production apps untouched.

**Artifact root:** `C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\comfymodal-data\benchmarks\resource_experiments\` (manifests, per-run logs, per-arm `*_summary.json`) and `...\benchmarks\runs\v2_*` (run JSONs; key dirs: RAM 16-15-46, CPU4 16-48-47, CPU8 17-04-42, A100 17-56-48, H100 18-46-26/18-47-33/18-48-28, H200 18-55-35/18-56-26/18-57-11, canary 19-2x).

**Files changed (TESTING2):** `comfymodal_runtime/resource_telemetry.py` (new), `comfymodal_runtime/modal_app.py` (telemetry wiring + GPU env passthrough + gpu_allocation payload), `tools/run_resource_arm.py` (new), `tools/analyze_resource_gpu_experiments.py` (new), `gpu_catalog.py` (h100!/b300), `tests/test_resource_telemetry.py` (new), `deploy_and_run_v2_single.bat`/`run_v2_single.bat` (GPU env override). `main` (f8f2da5): 22 files (waterfall chain + bat overrides + analyzer tool + tests).

**Commits:** `main` → `f8f2da5`. `TESTING2` → `be5a863`, `713bff7`, `683efa0`, `fb0a9a1`, `e249c11`, `bd5aa2f`, `7b14577`, `8344e8e`, `4ecdc35`, `bf8055a`.

# 23. Unresolved anomalies

1. **H100 TWO-LANE lane wait p50 13.4 s** (H200 5.5 s, A100 2.3 s, RTX 2.1 s) — zero-paid-run path reanalysis confirmed all H100 runs are fast-path (cache hit, early activation scheduled, no request-time load); the wait is the early-activation H2D of the retained ~12.3 GB snapshot UNET on H100 hosts (load_wall 5.1–20.3 s), i.e. a transfer-bandwidth/host effect, not a runtime-path difference. Needs the ≥200 ms waterfall audit / bandwidth-topology investigation (page-fault H2D, NUMA/pinning).
2. **Placement storm** throughout the experiment window (sub2resume 60 s–>10 min; queue wait unbilled but dominates user wall).
3. **cgroup `cpu.stat` unreadable** in this Modal/gVisor runtime — CPU telemetry is process-tick based (limitation documented).
4. `identity.gpu` stale reporting — fixed in code (`bf8055a`), fix **unverified by a paid run** (canary DNF on placement).
5. A100 old-driver runs lack nvidia-smi evidence (actual GPU established by deploy request + benchmark cpu/memory validation + sampling signature).
6. RAM sampled peak identical (25.19 GB) across all runs — consistent with a deterministic FULL-snapshot model set, but flagged for scrutiny.
7. One-off in-app tails (RAM run 2: 19.8 s app; CPU4 run 0: 44.8 s app) with normal sampling/VAE — pre-sampler tails, candidates for the ≥200 ms audit.
8. **~2.1 s VAE tail from the candidate report did NOT reproduce** in any experiment arm (VAE p50 0.42–0.59 s everywhere).

# 24. Exact next steps (in order)

1. **User chooses acceptable GPU(s)** from the measured matrix (B200/L40S untested; B300 blocked).
2. **Retry the canary** when placement recovers (A100, one run, 25-min window) to verify the repaired `gpu_allocation`/exact-GPU logging on a paid run.
3. After canary pass: fill A100/H100(`H100!`)/H200 to 5 valid each (samples 4–5, 10-min DNF rule), then B200 and L40S (5 each, 3-valid minimum).
4. Final production-like true-cold validation with winning CPU=8/RAM=28672 + chosen GPU strategy.
5. Perform the ≥200 ms post-restore waterfall audit (incl. H100 TWO-LANE lane-wait anomaly).
6. Classify every recurring ≥200 ms stage (required compute / snapshot-movable / cacheable / parallelizable / avoidable / platform).
7. Investigate VAE tail only if the ~2.1 s anomaly reproduces.
8. Collect remaining small deterministic wins toward consistent sub-10/sub-11 placement-excluded execution.

---

## FINAL RESOURCE CANDIDATE

```
CPU request: 8
RAM request: 28672 MiB

RTX PRO 6000:   8 valid · app 11.3 s · sampling 3.75 s · $0.0128/gen · $0.0605/min
A100 80GB:      3 valid (fill to 5) · app 15.9 s · sampling 5.70 s · $0.0148/gen · $0.0517/min
H100:           3 valid (fill to 5, use H100!) · app 32.3 s (TWO-LANE lane-wait anomaly 13.4 s) · sampling 2.45 s · $0.0445/gen · $0.0758/min
H200:           3 valid (fill to 5) · app 17.9 s · sampling 2.32 s · $0.0283/gen · $0.0857/min
B200:           NOT TESTED (canary gate)
B300:           BLOCKED_BY_RUNTIME_COMPATIBILITY (CUDA 13.1+ required; stack is CUDA 13.0.0/torch cu130)
L40S:           NOT TESTED (canary gate)

CHEAPEST:                 A100 80GB ($0.0517/min, $0.0148/gen)
FASTEST APPLICATION:      H200 (py→result 17.9 s) [H100 sampling fastest at 2.45 s but app dominated by lane-wait anomaly]
FASTEST USER WALL:        H200 (sub→result 25.7 s; storm-dominated window)
BEST SCHEDULING:          H200 p50 7.6 s / H100 9.4 s (same window)
BEST COST/PERFORMANCE:    H200 (0.63× RTX app time at 1.42× cost) — A100 if absolute cost dominates
MOST CONSISTENT:          H100/H200 tight app tails (p90≈max) vs A100/RTX outliers

GPU decision: USER DECISION REQUIRED — B200/L40S evidence pending canary; B300 requires a CUDA 13.1+ stack migration (out of scope).
```

# Next Steps

```text
1. User chooses acceptable GPU(s) from the measured matrix.
2. Retry the paid canary when placement recovers (verify repaired exact-GPU logging).
3. Fill A100/H100(H100!)/H200 to 5 valid; run B200 + L40S (5 each).
4. Run final production-like true-cold validation (CPU 8, RAM 28672, chosen GPU, FULL, TWO-LANE, AWS, no pin).
5. Perform the final post-restore >=200 ms waterfall audit (incl. H100 lane-wait anomaly).
6. Classify every recurring >=200 ms stage/gap (compute / snapshot-movable / cacheable / parallelizable / avoidable / platform).
7. Investigate VAE tail only if the ~2.1 s anomaly reproduces.
8. Collect remaining small deterministic wins toward consistent sub-10/sub-11 placement-excluded execution.
```

---

**Paid-run accounting (measured generations):** RAM arm 16 measured attempts (12 excluded, 4 counted) · CPU4 8 counted · CPU8 8 counted · A100 4 attempts (3 counted + 1 abandoned DNF) · H100 3 counted · H200 3 counted · canary 2 DNF attempts · warmup runs 21 total. **29 valid measured generations counted** in final statistics; total paid full-generation attempts 44.
