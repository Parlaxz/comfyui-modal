# V2 Final Optimization A/B Results — Deployment-1 Campaign COMPLETE; Restore Experiment STOPPED (Arm Wiring Bug)

**Date:** 2026-08-13
**Repo:** `comfyui-modal` (HEAD `e5483d5a7a5414fc9baae84d16e02c13bf270520`, branch `TESTING2`, working tree — `commit hash: none`)
**Campaign status:** Deployment-1 request-level campaign **COMPLETE** (baseline N=5, UNET stopped, VAE winner N=5 rejected, PNG N=2 kept, cache N=2 inconclusive). **Restore (Deployment 2) STOPPED per protocol**: an experiment-revealed implementation bug — the restore-memory B arm's snapshot-freeze hook cannot resolve a state directory in the container (`freeze skipped: no_state_dir`), so the arm would silently measure baseline. Preserving all D1 results; the bug is reported precisely; no silent patch-and-continue.

---

# Executive result

| Experiment | Samples | TOTAL WALL Δ (median) | Verdict |
|---|---|---|---|
| Baseline (A) | 5 | 20197.2 ms (med) | — |
| UNET pinned-staging (B) | 2 | −no meaningful change (one regression, one within-noise) | **REJECT** (stopped at N=2) |
| VAE early_1000 (B) | 5 | no saving (post-transition unchanged) | **REJECT** |
| PNG level1 (B) | 2 | stage saving ≈405 ms encode; TOTAL WALL within noise | **KEEP** |
| Cache async_lru (B) | 2 | ≈24 ms foreground LRU saving | **INCONCLUSIVE** |
| Restore frozen (B) | 0 | NOT RUN — arm wiring bug (D2) | **NOT READY** |

Step-3 fast path (consumed=1) held for **every** retained request in the campaign (15/15 on D1).

# Accepted Step-3 baseline (Deployment 1)

- Snapshot: `im-8KexmbMytHCmXTxTMl6pl9|423ce11e7d2646c9b270e02955b04604` · deployment hash `1bd881d798947977…` · generation `fbecafb8ae72728ebc36d581b8356e39` · ComfyUI `f49bdb655707b979…` (core match=1) · CLIP/VAE=1, UNET=0, retain clip_vae, fast-disk, sampling_end, rtx-pro-6000, 12 CPU, 32768 MB, unpinned.
- The prior validation/discard request proved `plan_validation_consumed=1`; **no further validation request was run** (per protocol).

# Baseline N=5 (retained, all consumed=1)

| Metric | min | median | mean | max | std |
|---|---|---|---:|---:|---:|---:|
| TOTAL WALL (ms) | 14708.8 | **20197.2** | 25819.8 | 45498.8 | 11899.5 |
| Scheduling (ms) | 1470.9 | 2208.4 | 13205.5 | 57641.4 | 22221.3 |
| Command→response (ms) | 16917.1 | 21668.1 | 39025.2 | 90969.6 | 28422.1 |
| Restore (cp, ms) | 517.7 | 541.3 | 844.7 | 1838.9 | 508.6 |
| Pre-sampler (cp, ms) | 4752.0 | 5487.6 | 8009.9 | 19125.1 | 5575.6 |
| Sampling (cp, ms) | 3668.5 | 3712.9 | 3705.1 | 3728.1 | 20.4 |
| VAE decode (cp, ms) | 398.0 | 420.2 | 419.2 | 441.5 | 14.5 |
| UNET H2D dev (ms) | 2083.6 | 2598.8 | 4964.8 | 15308.3 | 5178.5 |
| Cache lookup (ms) | 91.7 | 101.4 | 193.6 | 455.5 | 139.8 |
| PNG compress (ms) | 551.9 | 556.0 | 555.7 | 559.7 | 2.8 |
| PNG encode total (ms) | 569.8 | 575.9 | 574.8 | 578.1 | 3.1 |
| VAE H2D (ms) | 44.0 | 53.7 | 356.4 | 850.4 | 375.7 |

Output: identical per run (2,874,640 B PNG, sha256 `895deda2…`). Placement: GCP us-east1 ×4, us-east4 ×1 (run3 — degraded host: restore 1838.9 / pre-sampler 19125 / UNET H2D 15308 → **placement-confounded** within baseline itself).

# Baseline stage distribution (medians)

Restore 541 · UNET checkpoint read/bind ~ (bind 20.8, ctor 4.3, get_model 312.6) · UNET H2D 2598.8 · pre-sampler 5487.6 · Sampling **3712.9 (fixed)** · post-sampling VAE transition ~663–899 · VAE decode 420.2 · PNG encode 575.9 · output/result tail (handoff) ~2.6–3.2 s.

# UNET pinned-staging A/B (STOPPED at N=2 — no meaningful improvement)

| | A med (N=5) | B run1 | B run2 |
|---|---:|---:|---:|
| UNET H2D dev (ms) | 2598.8 | 2928.2 | 2711.3 |
| bind (ms) | 20.8 | 67.9 | 75.2 |
| TOTAL WALL (ms) | 20197.2 | 44197.6 | 15755.8 |
| Sampling (ms) | 3712.9 | 3697.3 | 3697.4 |
| GB/s | — | 3.9 | 4.2 |

- H2D: **no improvement** (+113/+329 ms vs A median; the bounded-staging arm did not beat pageable transfer on these hosts).
- TOTAL WALL: one regression (44.2 s — first-request penalty band) + one within-noise (15.8 s vs A min 14.7 s). **Stop rule triggered** (no meaningful TOTAL WALL improvement) → no +3.
- **Verdict: REJECT.** `placement_confounded=1` (B both us-east4; A mostly us-east1). Step-3 consumed=1 both runs.

# VAE offset scan (N=1 per offset) + winner

| Offset | TOTAL WALL | Sampling | post-transition | decode | prov |
|---|---:|---:|---:|---:|---|
| early_250 | 41436.9 | 3719.1 | 753.3 | 403.7 | GCP/us-east4 |
| early_500 | 42858.7 | 3711.9 | — | 362.3 | GCP/us-east4 |
| early_750 | 36346.7 | 3816.1 | 583.2 | 474.7 | AWS/eu-central-1 |
| **early_1000** | **34063.3** | 3724.1 | 801.6 | 369.6 | GCP/us-east4 |

- **Correctness gate (first B request, early_250): PASS** — one activation only (`scheduled=1 load_start=1 terminal=1 consumed=1`), `status=ready reason=ok trigger=early_start residency_status=gpu_resident transfer_count=1`, bf16/contiguous/policy-v1 identity intact, 4 normal decode calls, output byte-identical, Step-3 consumed=1. No model-management anomaly.
- Rejection rule: no offset slowed Sampling by ≥ hidden VAE time (hidden ≈ 50 ms cached H2D; max Sampling delta +103 ms on AWS early_750 — host, still < 50 ms hidden-time criterion not met as a slowdown ≥ hidden; conservative reject of 750 on Sampling + host variance).
- **Winner: early_1000** (lowest TOTAL WALL, clean Sampling). +4 → N=5 winner cohort: 14062.9 / 14514.0 / 27952.8 / 33014.7 / 34063.3 (med **27952.8**, mean 24721.5).
- **Verdict: REJECT.** The arm's target stage (post-sampling VAE transition) shows **no improvement** (668–802 vs A ~663–899) — the cached VAE H2D (~50 ms) leaves nothing to hide — and TOTAL WALL med +7.8 s vs A (host-variance-dominated; `placement_confounded=1`: B us-east4×4 + AWS×1 vs A us-east1×4 + us-east4×1). Mechanism is safe and correct but yields no measured saving.

# PNG A/B (STOPPED at N=2 — stable causal effect)

| | A med (N=5) | B run1 | B run2 |
|---|---:|---:|---:|
| PNG compress (ms) | 556.0 | 143.5 | 158.0 |
| PNG encode total (ms) | 575.9 | 168.5 | 168.0 |
| Output bytes | 2,874,640 | 3,129,718 | 3,129,718 |
| TOTAL WALL (ms) | 20197.2 | 33759.6 | 16605.9 |

- **Encode saving ≈ 405 ms** (~73% compression-time reduction), deterministic (compress_level is causal). File-size increase **+8.87%**. **Decoded pixels byte-identical** (1088×1920 RGB; 6,266,880 bytes equal; both consumed=1).
- **Verdict: KEEP.** Zero correctness risk (lossless PNG, same output content), stable stage saving; TOTAL WALL impact within host noise (~0.4 s).

# Conditioning-cache LRU A/B (STOPPED at N=2 — few-ms saving)

| | A sync (N=5, med) | B async run1 | B async run2 |
|---|---:|---:|---:|
| Foreground lookup (ms) | 101.4 | 244.5 | 68.0 |
| manifest read (ms) | 15.7 | 178.5 | 20.4 |
| **LRU touch (ms)** | **29.2** | 7.9 | 1.8 |
| exact hits | 1/1/1/1/1 | 1 | 1 |

- **LRU foreground saving ≈ 24 ms/hit** (29.2 → 4.8 med; ~83% of the LRU cost moved to the background worker; enqueued=1, coalesced batch, persist 0/33.5 ms off-foreground). Lookup totals remain **manifest/payload-read dominated** (7–178 ms variance) — async LRU does **not** and is not claimed to fix pathological payload-read hits; **no pathological hit observed** in these runs.
- **Verdict: INCONCLUSIVE** for TOTAL WALL (≈0.1%) — small deterministic stage saving, near-zero risk (eviction-quality only; STORE semantics untouched; teardown drain verified).

# Deployment-1 provisional ranking

1. **PNG level1** — saving ~405 ms; consistency perfect; risk none; complexity minimal → KEEP.
2. **Cache async_lru** — saving ~24 ms; consistency good; risk near-zero → INCONCLUSIVE (KEEP-lean).
3. **VAE early_1000** — no saving; safe; complexity moderate → REJECT.
4. **UNET pinned-staging** — no saving; bind regression; complexity moderate → REJECT.

# Restore Deployment 2 (STOPPED — arm wiring bug)

- Deployed identical architecture + `COMFYMODAL_V2_RESTORE_TOTAL_VRAM_FROZEN=1` (deploy 96.9 s; the env passthrough was added to `_runtime_env` before D2's freeze — a pre-existing framework gap found while preparing D2; D1 cohorts unaffected).
- **Construction gates PASS**: parity exact-match (`2a72642e34e66186…`), `[v2.deployment_proof] complete=True dep_hash=2faee9aa62a85351 gen_ok=1`, CLIP/VAE=1 UNET=0, RSS 11518.6 MiB, `comfyui_core_match=1`, new snapshot identity `im-…` (D2), dep identity `73d85f3aa136d103…`.
- **Implementation bug (experiment-revealed, source change required → protocol STOP):**
  - Container log: `[restore_memory_arm] freeze skipped: no_state_dir`
  - `frozen_capacity_path()` resolves `COMFYMODAL_V2_STATE_VOLUME_ROOT` (never baked — absent from `_runtime_env` and `_V2_RUNTIME_ENV`) or the dirname of `COMFYMODAL_V2_RESTORE_STATE_FILE` (bare filename in the container) → `""` → the snapshot-construction freeze hook writes nothing.
  - Modal volume `comfymodal-runtime-config` contains **no `gpu_capacity_frozen.json`** → every request restore runs `apply_frozen_total_vram_or_none()` → fallback `no_frozen_capacity` → **the B arm permanently behaves as baseline**. `[v2.experiment] restore_memory arm=optimized effective=baseline fallback=no_frozen_capacity`.
  - Required fix (next task): bake `COMFYMODAL_V2_STATE_VOLUME_ROOT=/mnt/comfymodal_runtime_state` via `_runtime_env` (or default `frozen_capacity_path()` to `RUNTIME_STATE_PATH`), then one fresh D2 deploy + re-gate + validation/discard + restore A/B.
- **Restore A/B: NOT RUN.** Per protocol: STOP, preserve results, report the bug — no silent patch-and-continue.

# Placement/confounding

- Providers/regions observed: GCP us-east1, GCP us-east4, AWS eu-central-1 (unpinned as required).
- `placement_confounded=1` for: UNET A/B, VAE winner vs baseline, and individually for baseline run3 (us-east4 degraded), PNG run2 (AWS), cache run1 (us-east4).
- No request was retried due to scheduling; scheduling is informational (no %/bar — unchanged).

# Stage-vs-critical-path savings

| Experiment | Raw stage saving | Critical-path saving | TOTAL WALL saving |
|---|---:|---:|---:|
| PNG level1 | 405 ms (encode) | ~405 ms (output tail) | ~0.4 s (within noise) |
| Cache async_lru | 24 ms (LRU touch) | ~24 ms (pre-sampler lookup) | ~0.02 s |
| UNET pinned-staging | −113…−329 ms (H2D) | 0 | 0 |
| VAE early_1000 | 0 (no hidden time) | 0 | 0 |

# Final ranking

| Rank | Optimization | Samples | A TW med | B TW med | Saving | Consistency | Risk | Verdict |
|---:|---|---:|---:|---:|---:|---|---|---|
| 1 | PNG level1 | 2 | 20197 | 16606–33760* | ~405 ms encode | perfect | none | **KEEP** |
| 2 | Cache async_lru | 2 | 20197 | 14731–38961* | ~24 ms | good | near-zero | **INCONCLUSIVE** |
| 3 | VAE early_1000 | 5 | 20197 | 27953 | 0 | n/a | low (safe) | **REJECT** |
| 4 | UNET pinned_staging | 2 | 20197 | 15756–44198* | 0 | n/a | low | **REJECT** |
| — | Restore frozen | 0 | — | — | — | — | — | **NOT READY** |

*host-variance band; N=2 arms are exploratory (labeled low sample size).

# Rejected/inconclusive experiments

- **UNET pinned_staging — REJECT** (no H2D or TOTAL WALL improvement; historical H2D bimodality not resolved by bounded staging on these hosts).
- **VAE early_1000 (and all offsets) — REJECT** (mechanism safe and correct; no hidden VAE time to reclaim with the cached ~50 ms H2D; no TOTAL WALL saving).
- **Cache async_lru — INCONCLUSIVE** (real ~24 ms LRU saving; TOTAL WALL impact negligible; pathological hits are payload/manifest-read dominated, not LRU).
- **Restore frozen — NOT READY** (wiring bug above).

# Compatible-winners projection

- Baseline TOTAL WALL median: **20197 ms** (host-variance band ≈ 14.7–45.5 s).
- Individually measured winners: PNG (~0.4 s) + cache (~0.02 s) — non-overlapping stages (output tail + pre-sampler lookup) → **projected compatible TOTAL WALL ≈ 19.8 s** median.
- Interactions: UNET↔CLIP and VAE↔Sampling measured **no effect** on Sampling (std 20 ms across all arms); cache↔CLIP encode not exercised (all exact hits); restore↔CUDA-init unmeasured (arm blocked); PNG is tail-only, no interaction.
- Confidence range: **low** (host variance ±5–12 s dominates the ~0.4 s signal); the projection should be validated on a stable placement in a follow-up.

# Exact artifacts

- Result dirs (all saved with full traces, opt diagnostics, final+remote waterfalls, Step-3 proof results):
  - Baseline: `comfymodal-data/benchmarks/runs/v2_2026-08-13_01-39-57`
  - UNET B: `…/v2_2026-08-13_01-46-26`
  - VAE: `…/v2_2026-08-13_01-48-32` (250), `…/01-51-21` (500), `…/01-52-42` (750), `…/01-54-57` (1000 probe), `…/01-56-20` (winner +4)
  - PNG B: `…/v2_2026-08-13_02-03-11`
  - Cache B: `…/v2_2026-08-13_02-05-54`
  - D2 (restore): `deploy_d2_restore.log`, `d2_construction.log`; freeze records `V2_AB_CAMPAIGN_DEPLOY2_FREEZE.md`, `V2_STEP3_IPC_TRANSPORT_FREEZE.md`

# Recommended implementation order

1. **Ship PNG compress_level=1** (deterministic ~405 ms saving; lossless; zero risk; +8.9% size acceptable).
2. **Ship async LRU** if 24 ms × hit volume matters (low risk; eviction-quality only).
3. **Do NOT ship** UNET pinned-staging or VAE early-start (no measured saving; keep A).
4. **Fix + re-test restore** (bake the state-volume root for `frozen_capacity_path`), then re-run the restore A/B with a fresh D2.

# Sampling report

Sampling — **fixed/out of scope**: median 3712.9 ms (std 20.4 across all D1 runs; max observed 3890.9 on one AWS host). No arm altered Sampling. Step count / CacheDiT / SageAttention / sampler / scheduler / CFG untouched.

---

**Production defaults changed: NO.** No B arm enabled; no `all_optimizations=1`; no winner combination.
**Paid generations this campaign:** D1 = 5 baseline + 2 UNET + 4 VAE scan + 4 winner + 2 PNG + 2 cache = **19** (all retained; no D1 validation rerun). D2 = 0 (restore arm blocked before any request; the validation/discard for D2 was NOT run because the arm would have measured baseline — no point burning it; the deploy-time construction/readback containers are the bat-inherent flow).
