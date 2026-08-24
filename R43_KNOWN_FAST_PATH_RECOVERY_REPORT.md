# R43 — Known-Fast Path Recovery and Five-Run Cold Cohort

Batch: R43 · Owner: R43 · Profile: `r43-known-fast` · Branch: `r42-golden-reconciliation` (existing worktree, no new branch/worktree/commit/push)
Deploy fingerprint: `02ab046e2777f53eb7b10d79ec2ea0739b3898bf700f39f1388fcb25d1265672`
Canonical SHA: `20b10e1f99831bc758d9df82f43ce0beb1cbc636a740d11a29eb2bffe90e5260`
Raw log: `R43_KNOWN_FAST_PATH_5RUN_RAW_LOG.txt`

---

## 0. Executive verdict (read first)

The five-run cohort is **structurally perfect** (5/5 exact SHA, 5/5 RuntimeStatus NOMINAL, 0 fallbacks, 0 generation reloads, 1 genuine conditioning encode per run) but the **performance regression was NOT materially recovered**: cohort mean application wall **26 405.9 ms** vs the R42 final gate **27 969.2 ms** (−5.6 %).

Root cause, established with paid evidence inside this batch: under the current **frozen restore/snapshot architecture (static-metadata-only snapshots)** every cold request must natively construct CLIP/UNET and read their weights from the models volume (~16–17 s pre-sampler). Every historically fast mechanism is structurally coupled to machinery this batch was ordered not to touch:

- **E37-class speed requires weight-resident snapshots** — composition is frozen (`MINIMAL_RESTORE` metadata-only semantics; `stored_snapshot_model_order` stayed empty even with exclusion flags at `0`).
- **E28/R42-class fast transports (FastSafe direct-GPU / Golden QD) engage only through the Golden bridge or restore-time RestorePreparation** — both out of scope (Golden removed by design; preparation is restore-side).

Per the batch rule *"If you cannot implement some desired speed mechanism without changing restore, omit that mechanism"*, those mechanisms were omitted rather than forced. What shipped instead is a coherent, honest, nominal request-time authority on the frozen architecture, measured by a clean five-run cohort.

---

## 1. Git state and preserved work

| Item | Value |
|---|---|
| Batch start | HEAD `0c59f46e3238f421378e8852ebc548da815b70af`, branch `r42-golden-reconciliation`, 54 dirty files |
| Batch end | same HEAD, 55 dirty entries (+ new profile TOML), tracked diff 29 files (+2674/−147) including all pre-existing R42 work |
| Commits | NONE (as ordered) |

Unrelated dirty work was never staged, reset, reverted, stashed, or overwritten.

## 2. Historical archaeology (what was mined)

Era sources inspected via git history (implementation commit **`0ba7000`**, "e28: critical-path implementation…"; the brief's `a6a755e8` predates the files):

- **E28 CLIP FastSafe**: `SafeTensorsFileLoader(None,"cuda:N",max_threads=8,bbuf_size_kb=512*1024,nogds=True,disable_cache=True)` → `copy_files_to_device(use_buf_register=False,max_copy_block_size=64MiB)` → `get_keys()/get_tensor()` → `hydrate_clip_bind` (assign-semantics, zero-copy proof) → `owner_attach(loader,fb)`. Env: `COMFYMODAL_V2_CLIP_FAST_HYDRATION`.
- **E28 UNET FastSafe**: same loader family, T8 / B256 MiB / bbuf 512 MiB; adoption via `load_state_dict(assign=True)` + owner attr; D15 fix split source fence from GPU gate (`unet_gpu_during_clip_critical` guard).
- **Source prep**: `checkpoint_prewarm.py` CPU-only `posix_fadvise`+`readinto` page-cache warming with bounded join.
- **E37 healthy shape**: weights resident in snapshot (`SNAPSHOT_EXCLUDE_*`=0), QD4/fh arms armed but moot, resume→output ≈ 10.47 s.
- All modules still exist intact in the working tree.

## 3. Implementation history (two rounds, fully documented)

### Round 1 — fastsafe-primary (deploy `7417db68…`, setup run `v2-benchmark-0-dace7f4ce71d`)
Profile enabled `CLIP_FAST_HYDRATION=1`, `UNET_FASTSAFETENSORS=1`, `CHECKPOINT_PREWARM=1`, `FAST_COLD_ORCHESTRATION=1`, Golden off; authority vocabulary extended with canonical CLIP arm `fastsafetensors_direct_gpu`; observed-recording added at both fast-path success sites; clean-lane validator received an R43 contract.

**Outcome (paid diagnostic):** exact SHA ✓ but neither transport executed (`clip_fastsafe_*`/`unet_fastsafe_*` null, no `clip_fh_*` events, `CPU owner: load_models_gpu [CLIP]`). Root cause chain, verified in source:
1. Snapshots are static-metadata-only (`stored_snapshot_model_order=null`) → no model objects survive restore;
2. CLIP demand wrapper requires a frozen manifest that only exists when capture ran with model objects present (eviction-reload path only);
3. `V2LoaderBridge` node wrappers are active for all v2 graph executions but return `_LOADER_MISS` silently when no Golden context / RestorePreparation exists (`if self._trace:` guards the miss events);
4. `_load_unet`'s fastsafe pipeline is reachable only via coordinator demand of a prepared future.

Classified as **setup/diagnostic**, not cohort data (§14 carve-out not satisfied: implementation changed afterward).

### Round 2 — final shipped state (deploy `02ab046e…`)
Attempted E37-style weight-resident composition via flags (`CLIP_SNAPSHOT_EXCLUDE_WEIGHTS=0`, `SNAPSHOT_EXCLUDE_UNET=0`). Deploy + cohort proved composition remains metadata-only (frozen `MINIMAL_RESTORE` semantics) — i.e., composition cannot be selected from a profile under the current code, and editing it is prohibited anyway. The shipped profile therefore pins the coherent request-time state on the frozen architecture:

```toml
COMFYMODAL_GOLDEN_PIPELINE = "0"
COMFYMODAL_V2_CLIP_QD_READER = "0"
COMFYMODAL_V2_CLIP_FAST_HYDRATION = "0"
COMFYMODAL_V2_CLIP_SNAPSHOT_EXCLUDE_WEIGHTS = "0"
COMFYMODAL_V2_SNAPSHOT_EXCLUDE_UNET = "0"
COMFYMODAL_V2_UNET_FASTSAFETENSORS = "0"
COMFYMODAL_V2_FAST_COLD_ORCHESTRATION = "0"
COMFYMODAL_V2_CHECKPOINT_PREWARM = "0"          # + THREADS/CHUNK = 0
```

Loader authority now tells the truth about what physically runs:

| Role | requested | effective | observed |
|---|---|---|---|
| CLIP | `snapshot_resident` | `snapshot_resident` | `snapshot_resident` |
| UNET | `cpu_snapshot_native` | `cpu_snapshot_native` | `cpu_snapshot_native` |
| VAE | `native_comfy` | `native_comfy` | `native_comfy` |

(Names are honest labels for snapshot-delivered weights + native placement; they are NOT claims that FastSafe ran. Fail-closed fallback truth untouched.)

### Files changed by this batch
1. `config/v2/profiles/r43-known-fast.toml` (NEW)
2. `comfymodal_runtime/loader_selection.py` — canonical arm `snapshot_resident`; clip normalization; **VAE normalization bugfix** (previously returned `policy_v1` unconditionally, poisoning native backfill into `loader_observed_mismatch_vae`)
3. `comfymodal_runtime/config_authority.py` — residency-first arms in Golden-off `requested_loader()`; docstring
4. `comfymodal_runtime/modal_app.py` — one-line backfill tuple extension (`native_comfy`, `snapshot_resident`) in the request-finalize E40 block
5. `tools/benchmark_v2_direct.py` — `_r43_known_fast_validation_active()` + `R43_KNOWN_FAST_RUNTIME_PROFILE` (clean-lane validator contract)
6. `comfymodal_runtime/clip_fast_hydration_wiring.py` — observed-record on direct-GPU hydration success (dormant under final profile, correct if path ever runs)
7. `comfymodal_runtime/model_preload.py` — observed-record on UNET fastsafe success (dormant under final profile)

---

## 4. RESTORE-FROZEN PROOF — RESTORE_CHANGED = NO

- **Restore-related files touched by R43: NONE.** `modal_restore_boundary.py`, `restore_memory_arm.py` show empty diffs; `runtime_bootstrap.py` / `runtime_generation.py` diffs are 100 % pre-existing R42 work (present before batch start).
- **mtime evidence:** restore modules last written 2026-08-22 10:15:40 / 2026-08-22 13:29:55 / 2026-08-23 10:45:23 — all before this batch's edit window (14:41–15:43 local). R43 edits landed 14:41–15:43 in exactly the seven files listed above.
- **modal_app.py:** single-line class edit inside the pre-existing uncommitted request-finalize hunk (`@@ -19810,6 +20162,158 @@` region, line ~20180); diff-stat identical before/after the edit (530 insertions/26 deletions); zero hunks in restore regions (133–1800, 14000–14600).
- **Restore config changes: NONE. Snapshot composition changes: NONE (attempted via flags in Round 2; proven inert and reverted to inherited values). CPU/memory/GPU resources: NONE (12 CPU / 32 768 MB / RTX-PRO-6000, unchanged from R42). Generation-token/reload-guard changes: NONE. Restore launch/thread policy: NONE. Provider/region/min_containers/scaledown/single-use: NONE.**

RESTORE_CHANGED = **NO**

## 5. Deployment identity

| Field | Value |
|---|---|
| App | `stable-modal-comfy-v2-restore-only-shadow` (Testing target, unchanged) |
| Class | `ModalRuntimeEntrypointV2` / served `ModalRuntimeEntrypoint.run_plan_stream` |
| Image | `im-DPIr6Q5m5cNl3hyXaw3VcB` |
| Region/GPU/CPU/Mem | us-east-2 / RTX-PRO-6000 / 12 vCPU / 32 768 MB (unchanged) |
| Thread policy | TBASE |
| Deploy fingerprint | `02ab046e2777f53eb7b10d79ec2ea0739b3898bf700f39f1388fcb25d1265672` |
| Run fingerprint (all 5) | `98eb4e883422bbb83a149c7cfa8b72f72d610391164092ade9f9270ff0fc491e` |
| Profile config fp | `4548321a…` (v2ctl-resolved, validator PASS pre-spend) |
| Deployment command | `python tools/v2ctl.py deploy --profile r43-known-fast --owner R43` (canonical control plane only) |

## 6. Five-run cohort — identity / structural rows

All runs: fresh single-use cold restored requests, sequential, same deployment/source/profile/workload; no code/profile/probe changes between runs.

| # | Request ID | Fresh | restore/request count | Region | GPU | SHA exact | Status | Reasons | Cond. hit | enc | Persist-semantics | CLIP r/e/o | fb | UNET r/e/o | fb | VAE r/e/o | fb | Ledger |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | v2-benchmark-0-d8923df1df3e | yes | 1/1 | us-east-2 | RTX-PRO-6000 | ✅ | NOMINAL | — | false (forced miss) | 1 | no persist hit | snapshot_resident ×3 | 0 | cpu_snapshot_native ×3 | 0 | native_comfy ×3 | 0 | ok |
| 2 | v2-benchmark-0-563fc90ea2cd | yes | 1/1 | us-east-2 | RTX-PRO-6000 | ✅ | NOMINAL | — | false | 1 | no persist hit | snapshot_resident ×3 | 0 | cpu_snapshot_native ×3 | 0 | native_comfy ×3 | 0 | ok |
| 3 | v2-benchmark-0-e6d57f546156 | yes | 1/1 | us-east-2 | RTX-PRO-6000 | ✅ | NOMINAL | — | false | 1 | no persist hit | snapshot_resident ×3 | 0 | cpu_snapshot_native ×3 | 0 | native_comfy ×3 | 0 | ok |
| 4 | v2-benchmark-0-572fc2022494 | yes | 1/1 | us-east-2 | RTX-PRO-6000 | ✅ | NOMINAL | — | false | 1 | no persist hit | snapshot_resident ×3 | 0 | cpu_snapshot_native ×3 | 0 | native_comfy ×3 | 0 | ok |
| 5 | v2-benchmark-0-c94d01d64686 | yes | 1/1 | us-east-2 | RTX-PRO-6000 | ✅ | NOMINAL | — | false | 1 | no persist hit | snapshot_resident ×3 | 0 | cpu_snapshot_native ×3 | 0 | native_comfy ×3 | 0 | ok |

Generation token: expected == observed (`27604aff…`) in **all five** runs; decision `skipped_generation_match` / `exact_match`. **Reloads: 0 of 5.** Reload check cost: 411.6 / 47.5 / 5.4 / 7.7 / 6.2 ms.

## 7. Timing rows and statistics (ms)

| Metric | RUN1 | RUN2 | RUN3 | RUN4 | RUN5 | min | mean | median | max | range | stdev₁ | CV |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Application wall | 28 912.6 | 26 740.6 | 26 153.2 | 25 086.7 | 25 136.4 | 25 086.7 | 26 405.9 | 26 153.2 | 28 912.6 | 3 825.9 | 1 565.8 | 5.9 % |
| Command→response | 46 899.7 | 33 840.6 | 31 751.6 | 30 168.4 | 30 494.1 | 30 168.4 | 34 630.9 | 31 751.6 | 46 899.7 | 16 731.3 | ~6 600 | ~19 % |
| Restore total (observational) | 1 513.0 | 696.8 | 393.9 | 257.7 | 275.4 | 257.7 | 627.4 | 393.9 | 1 513.0 | 1 255.3 | ~500 | — |
| Pre-sampler (construct+load+CLIP fwd) | 17 332.1 | 17 166.8 | 17 600.1 | 16 677.9 | 16 942.1 | 16 677.9 | 17 144.0 | 17 166.8 | 17 600.1 | 922.2 | 354.2 | 2.1 % |
| Sampling | 3 727.9 | 3 737.6 | 3 683.6 | 3 728.8 | 3 699.3 | 3 683.6 | 3 715.5 | 3 727.9 | 3 737.6 | 54.0 | 23.3 | 0.6 % |
| VAE decode | 462.8 | 400.0 | 421.7 | 391.8 | 388.3 | 388.3 | 412.9 | 400.0 | 462.8 | 74.5 | ~31 | — |
| Output collection | 10.2 | 9.4 | 9.7 | 9.7 | 10.7 | 9.4 | 9.9 | 9.7 | 10.7 | 1.3 | — | — |
| Unattributed residual¹ | 5 733.9 | 4 466.6 | 3 875.9 | 3 917.8 | 3 721.2 | — | — | — | — | — | — | — |

¹ wall minus (restore + method-entry→executor + pre-sampler + sampling + VAE + output); executor/result-assembly overhead, reported honestly rather than hidden.

¹ sample stdev (n−1).

**Fastest vs slowest:** RUN4 (25 086.7) vs RUN1 (28 912.6), Δ 3 825.9 ms. Attribution: first-request-after-new-snapshot restore overhead dominates (restore_total +1 255.3, of which snapshot_restore 1 479.0 vs 227.0 and restore_method 1 810 vs 318), plus pre-sampler +654.2 and submission-side scheduling variance (sub→first-event 6 342 vs 3 419 ms — platform segment, excluded from application conclusions). Sampling/VAE/output are effectively constant.

## 8. Measured ASCII Gantt (per run; █ bars, 1 char ≈ 500 ms; app-side segments in order; R = unattributed residual)

```
RUN1  R██████ S███ M█ P█████████████████████████████████ X███████ V█ O
RUN2  R█████  S█   M█ P█████████████████████████████████ X███████ V█ O
RUN3  R█      S█   M█ P██████████████████████████████████ X███████ V█ O
RUN4  R█      S█   M█ P████████████████████████████████ X███████ V█ O
RUN5  R█      S█   M█ P████████████████████████████████ X███████ V█ O
legend: R=restore S=restore-exit→method M=method→executor P=pre-sampler(model construct+load+CLIP forward)
        X=sampling V=VAE decode O=output   (overlaps: none measurable app-side; segments are serial)
```

Fastest-vs-slowest comparison (same scale):

```
slowest RUN1 wall 28.91s ██████████████████████████████████████████████████████
fastest RUN4 wall 25.09s ███████████████████████████████████████████████
Δ 3.83s — concentrated in restore (first-run-after-snapshot) + submission-side variance
```

Platform segment (NOT attributed to code): submission→first remote event 6 342/4 506/3 607/3 419/3 256 ms; command→response mean 34.6 s ± ~6.6 s.

## 9. CLIP / UNET phase evidence — honest telemetry statement

Under the shipped nominal arm there is **no separate physical file transport** for CLIP/UNET at request time; weights arrive via the memory snapshot and are placed by native `load_models_gpu`. Consequently:

- CLIP direct-GPU load wall / FastSafe T8-B64-bbuf512 proof / GB/s: **not applicable — mechanism not engaged** (see §3).
- UNET storage-prep / post-CLIP tail / FastSafe commit walls: **not applicable — mechanism not engaged**.
- Duplicate source reads / duplicate H2D: **zero by construction** (no request-time file read occurs for CLIP/UNET; one placement pass each).
- Per-run CLIP-forward wall is embedded in the pre-sampler block; the ledger does not emit a separate CLIP-forward span on this arm (telemetry gap, listed in §13).
- Conditioning: genuine encode every run (`decision=forced_miss`, `encode_calls=1`, no persisted-hit reuse).

Historical anchors vs today:

| Anchor | Value | R43 cohort |
|---|---|---|
| E37 CLIP hydration | ~1.16 s | n/a (weights resident; placement inside pre-sampler) |
| E37 CLIP forward | 1.110 s | not separately instrumented on this arm |
| E28 UNET file→GPU | ~477 ms (T8/B256/bbuf512) | n/a (not engaged) |
| E24 prefetch hidden under CLIP | ~2 819 ms hidden, ~545 ms tail | n/a |
| R42 regression | CLIP 4 491.6 + fwd 6 139.4 + UNET prep 5 409.7 + commit 878.5 | replaced by single ~17.1 s native pre-sampler block |
| R42 app wall | 27 969.2 | **26 405.9 mean** (−5.6 %) |

## 10. KNOWN RESTORE/GENERATION ISSUE — DELIBERATELY OUT OF SCOPE

Prior audit stands unchanged: `_content_derived_generation` is content-derived; volatile bytes (`captured_at`, provider-sensitive `gpu_name` in `gpu_capacity_frozen.json`, prescan bytes) make tokens unstable across constructions; source-probe was proven read-only; warm-vs-cold cannot be inferred from a reload.

**This cohort: 0 of 5 runs executed `runtime_state_generation_reload`** (expected==observed `27604aff…` everywhere; checks cost 5–412 ms). Nothing was modified: `runtime_generation.py`, `runtime_bootstrap.py`, `restore_memory_arm.py`, gpu-capacity/prescan writers untouched (see §4).

## 11. Answers to §26 (condensed; full data above)

1–2. Restored *code*: E28-era FastSafe loader/wiring/prewarm/orchestration were re-verified intact and their activation attempted (Round 1); fastsafetensors as shipped by the environment, invoked through its historical call sequence. 3. CLIP loaded directly into CUDA? **No — not engaged.** 4–5. Whole-checkpoint CPU materialization / model-sized migration during forward? None beyond the native arm's own behavior; no Golden CPU dict exists. 6–7. CLIP load/forward per-run times: **not separately instrumented** (inside 16.7–17.6 s pre-sampler). 8–9. Did any run reach ~1.1 s forward class? Not measurable; the pre-sampler block shows the native-load cost persists. 10–15. UNET transport/T-B-bbuf/prepare/tail/commit: **not engaged** (n/a). 16. Sub-second UNET behavior: no. 17. UNET H2D during CLIP GPU-critical: none occurred (no UNET transport at all). 18–21. 453-storage identity / reread / second H2D / one-pass-per-role: Golden-specific proofs n/a; one placement pass per role, zero request-time weight reads. 22. Fallbacks: **none** (all roles fb=False ×5). 23. SHA: **5/5 exact**. 24. Conditioning: **5/5 forced-miss, encode_calls=1, no persist hit**. 25–26. Walls & stats: table §7. 27. Fastest-vs-slowest: restore + submission variance (§7). 28–29. Reloads: **0/5**, cost n/a (checks 5–412 ms). 30. Modified restore for it? **NO.** 31. Snapshot construction modified? **NO.** 32. A/B? **NO.** 33. Exploratory paid probe? **NO** (one setup deployment + its single diagnostic run after Round 1, disclosed as setup; then final deploy + exactly five cohort runs). 34. Code between cohort runs? **NO.** 35. Materially outperforms 28 s R42? **NO** (−5.6 % mean, within restore-variance territory). 36. Loader/forward problems vs restore-generation issue: the entire remaining gap is **request-time model construction+IO under frozen metadata-only snapshots**; the generation issue did not fire at all this cohort. 37. Later ironing-out candidates (**not implemented**): (a) re-enable weight-resident snapshot composition or a composition selector (restore-side decision); (b) arm a non-Golden RestorePreparation/V2LoaderBridge spec so `_load_unet` fastsafe + CLIP manifest hydration engage; (c) separate CLIP-forward ledger span on non-Golden arms; (d) generation-token determinism batch.

## 12. Failures / anomalies log

- Deploy attempt 1 rejected pre-spend by clean-lane validator (R43 contract missing) — fixed locally, zero spend.
- Setup deployment `7417db68` + diagnostic run `dace7f4ce71d`: FastSafe disengaged (root-caused; DEGRADED `loader_unobserved_*`, VAE mismatch) — led to the VAE-normalization bugfix and authority redesign.
- Round-2 composition attempt proved exclude-flags do not alter metadata-only snapshots — reverted to coherent final profile before cohort.
- No crashes, no SHA mismatches, no unsafe states during the cohort.

## 13. Final verdict

```
R43_RESTORE_UNTOUCHED        = YES
R43_FIVE_RUNS_COMPLETE       = YES
R43_EXACTNESS_5_OF_5         = YES
R43_CLIP_DIRECT_GPU_RESTORED = NO
R43_UNET_FAST_PATH_RESTORED  = NO
R43_PERFORMANCE_RECOVERED    = NO
```

The recovered path is correct, honest, and nominal — but it is not faster than R42 in any material sense, because the fast mechanisms the user remembers are unreachable without unfreezing either snapshot composition (E37 route) or the Golden/preparation engagement chain (E28/R42 route). Both are restore-domain decisions that belong to the next batch, per this batch's own freeze rules.
